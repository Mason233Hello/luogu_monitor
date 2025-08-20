# 洛谷私信提醒

### 如何下载

点进 `dist` 目录，然后下载里面的文件。一级目录里面有源代码。

## 网页端

转载自 - <https://blog.rockson.top/posts/luogu-si-xin-ti-xing/>

优势：上手简单，不用下载，（有可能全平台可用）。

劣势：需要打开 chat 窗口。在网络环境较差的时候如果 timeout 则需要刷新。且不会存档，即每次都需要操作一遍。

首先打开私信页面，然后将：

```js
let ws = new WebSocket("wss://ws.luogu.com.cn/ws");
Notification.requestPermission();
function showNotice(msg) {
    function  newNotify() {
        let notification = new Notification("新的私信", {
            dir: "auto",
            lang: "hi",
            requireInteraction: true,
            icon: "https://www.luogu.com.cn/favicon.ico",
            body: msg
        });
        notification.onclick = () => { 
            window.focus();
        }
    }
    //权限判断
    if (Notification.permission == "granted") {
        newNotify();
    } else {
        //请求权限
        Notification.requestPermission(function (perm) {
            if (perm == "granted") {
                newNotify();
            }
        })
    }
}
ws.onopen = () => {
    ws.send(`{"type":"join_channel","channel":"chat","channel_param":"${window._feInjection.currentUser.uid}","exclusive_key":null}`);
}
ws.onmessage = (e) => {
    let u = JSON.parse(e.data);
    console.log(u);
    if (u._ws_type === 'server_broadcast' && u.message instanceof Object && u.message.sender.uid !== window._feInjection.currentUser.uid) {
        showNotice(`${u.message.sender.name} : ${u.message.content}`);
    }
}
```

粘贴至**控制台**。**注意不要关闭私信页面。**

## 本地端

以下所有代码由 Deepseek 生成。

优势：本地存储，有存档，自动重新连接不怕超时。

劣势：需要拷贝 cookie，且只支持 windows。

### 如何复制 cookie

确保你在洛谷的任意页面。

首先点开 F12，打开开发者工具。找到 应用程序（edge）或者 Application（chrome），找到 cookie。按照提示将需要的 cookie 复制进去。

保证不窃取用户的任何 cookie。
