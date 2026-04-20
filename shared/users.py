import subprocess
import json

def get_users():
    posh = subprocess.run(['powershell','-command','get-localuser | select-object * | convertto-json'],capture_output=True, text=True) 
    users = json.loads(posh.stdout)
    return users