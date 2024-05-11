# MVS Automation Python Library

This library allows the use of MVS/CE in an automated fashion. This can
be used for deploying XMI files, pushing out updates, building software,
creating custom MVS deployments.

Using this library requires a recent version of hercules SDL and one of
MVS/CE, TK5, or TK4-.

**TK5/TK4-**: If you're using either TK5 or TK4-, they must be IPL'd before
hand. Adding auto IPL of those two flavors will come at a later date.

Example:

Submit JCL and check the results, attach a device
and send an operator command::

```python

import sys
from automvs import automation

if len(sys.argv) != 2:
    print("Usage: python go_mvs.py <MVS system> <MVS PATH> username password")
    print(" MVS system: one of MVSCE, TK4- or TK5\n MVS PATH: /path/to/the/system. E.g. /home/test/mvs/tk4-")
    sys.exit(1)

mvs_type = sys.argv[1]
folder = sys.argv[2]
username = sys.argv[3]
password = sys.argv[4]
punch_port = 3505
web_port = 8038
ip = '127.0.0.1'

build = automation(
                    system=mvs_type,
                    system_path=folder,
                    ip = ip,
                    punch_port = punch_port,
                    web_port = web_port,
                    username=username,
                    password=password
                  )

cwd = os.getcwd()

if mvs_type == 'MVSCE'
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
    if mvs_type == 'MVSCE'
        build.quit_hercules()
```