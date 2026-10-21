# Drive a running game started with NWII_CTRL=<dir>/ctrl.txt: write commands
# ("press NAME ms", "interp on|off", ...) plus "shot", wait for the screenshot
# and save it half-size as <dir>/now.png. ctl.py <dir> [command ...]
import sys,os,time
from PIL import Image
d=sys.argv[1]; cmds=sys.argv[2:]
ctrl=os.path.join(d,'ctrl.txt'); bmp=ctrl+'.bmp'
if os.path.exists(bmp): os.remove(bmp)
open(ctrl,'w').write('\n'.join(cmds+['shot'])+'\n')
for _ in range(200):
  time.sleep(0.1)
  if os.path.exists(bmp) and not os.path.exists(ctrl):
    time.sleep(0.3); break
im=Image.open(bmp); im.resize((im.width//2,im.height//2)).save(os.path.join(d,'now.png')); print('ok')
