// birdreport /front/ 公开接口助手（签名式，无需登录 token）。
// 用站点原版 jQuertAjax 的 format(排序JSON) / encrypt(RSA body) / decode(AES响应)，
// sign = md5(format_data + requestId + timestamp)。静默 console 避免污染 stdout。
// 用法: node front_helper.js <path> <urlencoded-params>   仅输出一行结果 JSON。
const fs = require('fs');
const https = require('https');
const noop = () => {};
['log', 'warn', 'error', 'info', 'debug', 'table', 'trace'].forEach(k => { try { console[k] = noop; } catch (e) {} });
// 直接 eval（模块作用域，require 可用；sloppy 模式下函数声明注入本作用域，后续可调用）
eval(fs.readFileSync(__dirname + '/jQuertAjax.js', 'utf8'));
const CryptoJS = require('crypto-js');
const md5 = (s) => CryptoJS.MD5(s).toString();

// 从 stdin 读 UTF-8 JSON {path, params}，避开 Windows argv 中文编码问题
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', (d) => { input += d; });
process.stdin.on('end', () => {
  let path, params;
  let token = '';
  try { const o = JSON.parse(input); path = o.path; params = o.params || ''; token = o.token || ''; }
  catch (e) { process.stdout.write(JSON.stringify({ error: 'bad stdin json' })); return; }

  const fmt = format(params);
  const body = encrypt(fmt);
  const ts = getTimestamp();
  const rid = getUuid();
  const sign = md5(fmt + rid + ts);
  const data = Buffer.from(body, 'utf8');

  const req = https.request({
    hostname: 'api.birdreport.cn', path: path, method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
      'Origin': 'https://www.birdreport.cn', 'Referer': 'https://www.birdreport.cn/',
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/146.0.0.0 Safari/537.36',
      'requestId': rid, 'sign': sign, 'timestamp': String(ts), 'Content-Length': data.length,
      ...(token ? { 'X-Auth-Token': token } : {}),
    },
  }, (res) => {
    let buf = '';
    res.on('data', (d) => { buf += d; });
    res.on('end', () => {
      let result;
      try {
        const j = JSON.parse(buf);
        // 返回原始密文 data，解密交给 Python（不同端点 AES key 可能不同）
        result = { code: j.code, count: j.count, msg: j.msg, data_raw: j.data };
      } catch (e) {
        result = { error: 'parse', raw: buf.slice(0, 200) };
      }
      process.stdout.write(JSON.stringify(result));
    });
  });
  req.on('error', (e) => process.stdout.write(JSON.stringify({ error: String(e) })));
  req.write(data);
  req.end();
});
