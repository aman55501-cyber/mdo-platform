const { app, BrowserWindow, shell } = require("electron")
const path = require("path")
const isDev = process.env.NODE_ENV === "development" || !app.isPackaged

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: "ANS MDO",
    backgroundColor: "#0d0f14",
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
    frame: true,
    autoHideMenuBar: true,
  })

  if (isDev) {
    win.loadURL("http://localhost:3000")
    win.webContents.openDevTools({ mode: "detach" })
  } else {
    win.loadFile(path.join(__dirname, "../out/index.html"))
  }

  // Open external links in browser
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: "deny" }
  })
}

app.whenReady().then(() => {
  createWindow()
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit()
})
