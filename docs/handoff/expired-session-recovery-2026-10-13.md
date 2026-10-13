# 登录过期后的邮箱恢复（2026-10-13，m5）

## 事件与目标

用户报告 mail.glocalstorage.cn 显示 Failed to fetch、邮箱列表全为 0。线上容器与数据库正常。
对应时间的登录代理日志确认会话 access token 已过期，且没有 refresh token；/oauth2/auth 返回 401，
Caddy 把 API 与资源请求转去登录流程，fetch 跟随到登录域后受跨域限制。0 不代表邮件丢失。
已向用户提供同源 /oauth2/start 的重新登录入口；保留原访问权限与会话有效期。

## 修复

- sessionFetch 对应用 API 使用 same-origin 凭据、manual 重定向；收到 opaqueredirect 或 401 时
  发布会话过期事件并返回明确错误，不把登录页当数据解析、不发送跨域 fetch、不自动导航或重试。
- 全站持久提示提供人工点击“重新登录”，返回当前完整邮件/视图 URL。普通 403 和网络错误保留原含义。
- 邮箱数据、附件、翻译、跟进、开发信和账号读取复用 helper；账号不再无限显示“正在读取”。
  列表说明重新登录后恢复；写请求包括发送不增加超时、重放或自动重试。
- 原邮件、模型任务、数据库、代理配置、登录凭据和刷新令牌权限均不改变。

## 验证与发布

完整 tools/precommit.sh 通过：756 后端测试、3 subtests、195 前端测试以及类型检查、lint、构建、全部守卫。
新增覆盖真实代理挑战形态、401、403 保留、原 headers/signal、写请求不重试、读取计时器清理、
登录链接和单一恢复提示。浏览器以正式 API 构建配合本机 302 模拟代理复现：显示登录恢复按钮，
无 CORS 错误、无自动跳转；桌面与 390px 手机均核对。没有用真实账户制造退出或发送测试邮件。
沿用已授权的 Git、CI SHA 发布、生产部署器备份/健康检查与 M5 同步流程。
入口：web/src/lib/session-auth.ts、components/session-notice.tsx、data/source.ts。
本机验证截图与发布凭证：~/.local/state/aimail/expired-session-recovery/。
