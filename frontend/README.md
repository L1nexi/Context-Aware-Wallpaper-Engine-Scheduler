# WEScheduler 产品界面

Vue 3、TypeScript、Tailwind CSS 4 和 shadcn-vue 工作区。该界面承载首次启动 setup，并将在完成后替换旧 Diagnostics Dashboard。

本地联调：

```powershell
python main.py --dashboard-api-port 38417
cd frontend
npm run dev
```

使用其他端口时，将 `DASHBOARD_API_PORT` 设置为相同值。验证命令：

```powershell
npm run type-check
npm run build-only
```
