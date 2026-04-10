/**
 * game-watch/scripts/fetch-ios-charts.js
 * 抓取七麦数据 iOS 榜单（畅销总榜、畅销游戏榜、免费总榜）
 *
 * 用法: node fetch-ios-charts.js [date YYYY-MM-DD] [-config <path>]
 * 输出: JSON 到 stdout
 */

const https = require('https');
const fs = require('fs');
const path = require('path');

// 解析命令行参数
const args = process.argv.slice(2);
let dateArg = null;
let configPath = path.join(__dirname, '..', 'game-watch-config.json');
for (let i = 0; i < args.length; i++) {
  if (args[i] === '-config' && args[i + 1]) configPath = args[++i];
  else if (/^\d{4}-\d{2}-\d{2}$/.test(args[i])) dateArg = args[i];
}

const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
const cookiePath = config.cookie_file;
const chartConfig = config.ios_charts;

function loadCookies(domain) {
  const content = fs.readFileSync(cookiePath, 'utf8');
  return content.split('\n')
    .filter(l => l.includes(domain) && !l.startsWith('#') && l.trim())
    .map(l => { const p = l.split('\t'); return p.length >= 7 ? p[5] + '=' + p[6].trim() : null; })
    .filter(Boolean)
    .join('; ');
}

function fetchBoard(brand, date) {
  return new Promise((resolve) => {
    const cookies = loadCookies('qimai.cn');
    const qs = new URLSearchParams({
      brand,
      country: chartConfig.country,
      genre: '0',
      device: chartConfig.device,
      date,
      page: '1'
    }).toString();

    const options = {
      hostname: 'api.qimai.cn',
      path: `/rank/index?${qs}`,
      headers: {
        Cookie: cookies,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        Referer: 'https://www.qimai.cn/',
        Accept: 'application/json'
      }
    };

    https.get(options, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          if (json.code === 10000 && json.rankInfo) {
            resolve(json.rankInfo.slice(0, chartConfig.top_n).map(r => ({
              rank: r.index,
              appId: r.app_id,
              name: r.appInfo?.appName || '',
              publisher: r.appInfo?.publisher || '',
              price: r.appInfo?.price || '0.00'
            })));
          } else {
            resolve({ error: json.msg || 'unknown error' });
          }
        } catch (e) {
          resolve({ error: 'parse error: ' + e.message });
        }
      });
    }).on('error', e => resolve({ error: e.message }));
  });
}

async function main() {
  const today = new Date();
  const date = dateArg || `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;

  const result = { date, charts: {} };

  for (const board of chartConfig.brands) {
    const data = await fetchBoard(board.id, date);
    result.charts[board.id] = { label: board.label, list: data };
  }

  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
}

main().catch(e => { console.error(e.message); process.exit(1); });
