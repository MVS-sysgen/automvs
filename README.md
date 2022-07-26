# MVS Automation Python Library

This library allows the use of MVS/CE in an automated fashion. This can
be used for deploying XMI files, pushing out updates, building software,
creating custom MVS deployments.

Using this library requires a recent version of hercules SDL and MVS/CE.

Example:

IPL MVS/CE and submit JCL and check the results, attach a device
and send an operator command::

```python
from automvs import automation
cwd = os.getcwd()
build = automation()
build.ipl(clpa=False)
try:
    print("Submitting {}/jcl/upload.jcl".format(cwd))
    with open("{}/jcl/upload.jcl".format(cwd),"r") as jcl:
        build.submit(jcl.read())
    build.wait_for_string("HASP250 UPLOAD   IS PURGED")
    build.check_maxcc("UPLOAD")
    build.send_herc('devinit 170 tape/zdlib1.het')
    build.wait_for_string("IEF238D SMP4P44 - REPLY DEVICE NAME OR 'CANCEL'.")
    build.send_reply('170')
    build.send_oper("$DU")
finally:
    build.quit_hercules()
```