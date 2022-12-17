# pungi容器化部署-fedora36


## 版本选定

![20221217_103441_59](image/20221217_103441_59.png)

![20221217_103514_96](image/20221217_103514_96.png)

择取2022年12月17日，fedora36最新版本**pungi-4.3.6-2.fc36.src.rpm**

















## 容器中为何找不到doc？

![20221217_111521_47](image/20221217_111521_47.png)

容器中，pungi包对应的doc为何没有，但是包校验又都是正常？

![20221217_111821_30](image/20221217_111821_30.png)

但是直接拆解又能看到doc相关内容


<https://man7.org/linux/man-pages/man8/rpm.8.html>
rpm帮助命令里是有忽略文档的选项

```
       --excludedocs
              Don't install any files which are marked as documentation
              (which includes man pages and texinfo documents).
```


![20221217_112431_40](image/20221217_112431_40.png)

* <https://bugzilla.redhat.com/show_bug.cgi?id=966715> 找到了，因为dnf.conf中有一个标准为，忽略docs

![20221217_113621_23](image/20221217_113621_23.png)

删除配置，重新安装，文件就有了



---
