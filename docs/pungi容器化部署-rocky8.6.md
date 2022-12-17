# pungi容器化部署-rocky8.6





















## rocky8.6 pungi 依赖 python3-fedmsg

![20221217_101322_30](image/20221217_101322_30.png)

![20221217_101417_27](image/20221217_101417_27.png)

pungi-utils 一些组件是需要 fedmsg ，但是rocky并没有提供

![20221217_101502_81](image/20221217_101502_81.png)


![20221217_101610_80](image/20221217_101610_80.png)

fedmsg 是什么？

```
fedmsg (Federated Message Bus) is a library built on ZeroMQ using the PyZMQ Python bindings. fedmsg aims to make it easy to connect services together using ZeroMQ publishers and subscribers.
```


![20221217_101740_53](image/20221217_101740_53.png)

* <https://github.com/fedora-infra/fedmsg>


![20221217_102024_48](image/20221217_102024_48.png) 













---
