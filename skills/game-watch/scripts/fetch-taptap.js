/**
 * game-watch/scripts/fetch-taptap.js
 * 抓取 TapTap 游戏数据（评分、关注、评论数等）
 *
 * 用法: node fetch-taptap.js [-config <path>]
 * 输出: JSON 到 stdout
 */

const https = require('https');
const fs = require('fs');
const path = require('path');
const { randomUUID } = require('crypto');

// 解析命令行参数
const args = process.argv.slice(2);
let configPath = path.join(__dirname, '..', 'game-watch-config.json');
for (let i = 0; i < args.length; i++) {
  if (args[i] === '-config' && args[i + 1]) configPath = args[++i];
}

const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
const cookiePath = config.cookie_file;

function loadCookies(domain) {
  const content = fs.readFileSync(cookiePath, 'utf8');
  return content.split('\n')
    .filter(l => l.includes(domain) && !l.startsWith('#') && l.trim())
    .map(l => { const p = l.split('\t'); return p.length >= 7 ? p[5] + '=' + p[6].trim() : null; })
    .filter(Boolean)
    .join('; ');
}

function fetchTapTapGame(appId) {
  return new Promise((resolve) => {
    const cookies = loadCookies('taptap.cn');
    const xua = `V=1&PN=WebApp&LANG=zh_CN&VN_CODE=115&VN=0.1.0&LOC=CN&PLT=PC&DS=Android&UID=${randomUUID()}&CURR=&DT=PC&OS=Windows&OSV=NT+10.0.0`;

    const options = {
      hostname: 'www.taptap.cn',
      path: `/webapiv2/app/v4/detail?id=${appId}`,
      headers: {
        Cookie: cookies,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        Referer: `https://www.taptap.cn/app/${appId}`,
        Accept: 'application/json',
        'X-UA': xua
      }
    };

    https.get(options, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          const app = json.data;
          if (!app || !app.title) { resolve({ error: 'not found', appId }); return; }

          const stat = app.stat || {};
          resolve({
            appId,
            title: app.title,
            rating: stat.rating?.score ?? null,
            fans: stat.fans_count ?? null,
            reviews: stat.review_count ?? null,
            reserves: stat.reserve_count ?? null,
            wishes: stat.wish_count ?? null,
            feedCount: stat.feed_count ?? null,
            url: `https://www.taptap.cn/app/${appId}`
          });
        } catch (e) {
          resolve({ error: 'parse error: ' + e.message, appId });
        }
      });
    }).on('error', e => resolve({ error: e.message, appId }));
  });
}

async function main() {
  const games = config.tracked_games || [];
  const taptapGames = games.filter(g => g.taptap_id);

  if (!taptapGames.length) {
    console.log(JSON.stringify({ error: 'no taptap games configured' }));
    return;
  }

  const now = new Date().toISOString();
  const results = await Promise.all(taptapGames.map(g => fetchTapTapGame(g.taptap_id)));

  const output = {
    fetched_at: now,
    games: results
  };

  process.stdout.write(JSON.stringify(output, null, 2) + '\n');
}

main().catch(e => { console.error(e.message); process.exit(1); });
