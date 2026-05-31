# birdreport token 一键提取书签（bookmarklet）

免去 F12 → Network → 找请求 → 复制头 的繁琐。登录后**点一下书签**即可抠出 token。
原理：token 是 32 位大写十六进制，JS 要把它塞进 X-Auth-Token 头，所以一定存在
localStorage / sessionStorage / 非 httpOnly cookie 里——书签按这个特征扫出来并复制到剪贴板。

## 安装（一次性）

1. 浏览器随便新建一个书签（收藏夹里右键"添加书签"）。
2. 名称填：`抓鸟token`
3. **网址(URL)** 填下面这一整行（包括开头的 `javascript:`）：

```
javascript:(function(){var p=/[0-9A-F]{32}/g,s=new Set();function scan(st){try{for(var i=0;i<st.length;i++){var v=st.getItem(st.key(i))||'';var m=v.match(p);if(m)m.forEach(function(x){s.add(x)});}}catch(e){}}scan(localStorage);scan(sessionStorage);(document.cookie.match(p)||[]).forEach(function(x){s.add(x)});var a=Array.from(s);if(a.length===1){if(navigator.clipboard)navigator.clipboard.writeText(a[0]);window.prompt('birdreport token（已复制到剪贴板）:',a[0]);}else if(a.length>1){window.prompt('找到多个候选，复制最像 token 的那个:',a.join('\n'));}else{alert('未找到 token，请确认已登录 birdreport.cn 后再点');}})();
```

## 用法（每次 token 过期时）

1. 浏览器登录 https://www.birdreport.cn/ （填验证码，正常登录）
2. 点收藏夹里的 **`抓鸟token`** 书签
3. 弹窗显示 token、并已复制到剪贴板
4. 把它交给刷新流程：
   - 直接对 Claude 说："**新 token 是 \<粘贴\>，刷新一下**"，或
   - 自己跑：`powershell -File <此skill>\scripts\refresh_birdreport_token.ps1 -Token <粘贴>`
5. 飞书发 `/new`

## 备注

- 若弹窗显示"多个候选"，挑最像 token 的（通常和你以前用的格式一致，纯大写字母+数字 32 位）。
- 若提示"未找到"，确认确实已登录；个别浏览器禁用 `navigator.clipboard` 时，手动从弹窗里选中复制即可。
- 想更进一步（点书签直接触发刷新、连粘贴都省）：可做"书签 → 本地监听端口 → 自动跑刷新脚本"，但要常驻一个本地小服务，且有跨域/混合内容的坑，性价比一般。需要再说。
