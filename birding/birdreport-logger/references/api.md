# birdreport.cn 接口细节（逆向记录）

本文件记录提交记录所需的全部接口、字段、加密与 ID 体系，方便日后排查或站点改版时更新。

## 鉴权与加解密

- 所有请求走 `https://api.birdreport.cn`，请求头带 `X-Auth-Token`（登录后浏览器 DevTools 复制，会过期）。
- **请求体为明文 JSON**（写操作和多数读操作都是）。
- **响应 `data` 字段**：列表大时直接是明文数组；否则是 **AES-256-CBC + base64** 密文。
  - key=`C8EB5514AF5ADDB94B2207B08C66601C`（16 进制样式的 32 字节 utf8 串，作 AES-256）
  - iv=`55DD79C6F04E1A67`
  - padding=PKCS7。常量取自站点 `https://www.birdreport.cn/assets/js/aes.util.js`（混淆存储）。
  - 站点改版可能更换 key/iv：在 aes.util.js 里找两个 base64 常量，base64 解码得到一串两位数字，每两位按十进制转字符即还原。

## 提交流程（两步）

### 1. 建活动 `POST /member/system/activity/saveReport`
请求体：
```json
{
  "point": {"point_id":"3","point_name":"上海植物园","province_name":"上海市",
            "city_name":"上海市","district_name":"徐汇区","adcode":"310104",
            "longitude":"121.45694","latitude":"31.15285","altitude":"",
            "member_id":<member_id>,"isopen":0},
  "activity": {"id":"","start_time":"2026-05-29 07:00:00","end_time":"2026-05-29 09:00:00",
               "state":"1","note":"","keywords":"","domain_type":0,"member_id":<member_id>},
  "units_activity": []
}
```
返回里含新建的 `activity_id`。`units_activity` 留空——鸟种走第 2 步。state 用 "1" 实测可成完整记录。

### 2. 逐鸟种 `POST /member/system/record/push`（每种一次）
```json
{"uuid":"<随机uuid>","type":1,"activity_id":"2120280","point_id":"3",
 "taxon_id":4866,"taxon_name":"白头鹎","taxon_count":"1",
 "member_id":<member_id>,"note":"","ctime":"2026-05-30 00:42:22"}
```
push 完即完整，无需额外"最终确认"调用（实测活动 2120280 提交后鸟种正常入库、可在记录中查到）。

## ID 体系（关键坑）

- **鸟种 taxon_id 有多个分类版本**：`/member/system/taxon/list` 返回全部版本，白头鹎旧版 G3=769、当前版 **Z4=4866**。提交必须用**当前版本（Z4，id 4001–5521，约 1519 种，名字唯一）**的 taxon_id。
  - `taxonomy.json` 已按 Z4 过滤缓存好；改版时按新 version 前缀重建。
  - 注意 `taxon/list` 对 name/keyword 等过滤参数**不生效**，需取回全量本地匹配。
- **点位 point_id**：官方热点是小 id（上海植物园=3、世纪公园=120）。
  - 按 id 取完整点对象：`POST /member/system/point/get {"point_id":3}`（saveReport 的 point 用它填）。
  - 按名字模糊找用户/社区点：`POST /member/system/point/list {"point_name":"世纪公园"}`（返回高 id 变体点）。
  - `point/hots` 返回热门热点但**不按关键字过滤**（忽略参数）。

## 其它有用读接口（供 birdwatching-guide 攻略用）

- `POST /member/system/activity/search`：按 `province/city/startTime/endTime` 搜报告（返回 point_name/区县/taxon_count/时间）。注：当前 token 下返回的是**本人**报告。
- `POST /member/system/record/search {"activity_id":N}`：取某报告的鸟种明细（字段是 `activity_id`，不是 `activityid`；旧文档里的 `activity/searchTaxon` 是占位错误，404）。`record/taxon` 亦可。
- `POST /member/system/record/searchTaxon`：返回带 taxon_id 的鸟种（过滤参数同样不生效，返回固定集）。

## member_id 来源

本账号 member_id=<member_id>（saveReport/push/point 都要带）。换账号需更新 `BIRDREPORT_MEMBER_ID`。
