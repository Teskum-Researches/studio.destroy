import requests
import time
import re
import threading
from http.cookies import SimpleCookie
from datetime import datetime, timedelta, UTC
import sys
from PyQt5.QtWidgets import QApplication, QAction, qApp, QMainWindow
from PyQt5 import uic

def log(message):
    window.log.addItem(message)
    window.log.scrollToBottom()

def login(username, password):
    session = requests.Session()
    session.get("https://scratch.mit.edu/csrf_token/")
    csrf_token = session.cookies.get('scratchcsrftoken')
    headers = {
        "referer": "https://scratch.mit.edu",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrf_token,
        "Content-Type": "application/json",
        "Accept-Language": "ru-RU,ru;q=0.9"
    }
    body = {
        "username": username,
        "password": password,
        "useMessages": "true"
    }
    respo = session.post(
        "https://scratch.mit.edu/accounts/login/",
        headers=headers,
        json=body
    )
    if respo.status_code == 200:
        cookies = respo.cookies
        for cook in cookies:
            if cook.name == 'scratchsessionsid':
                cookie_string = cookie_to_string(cook)
        match = re.search(r'([^=]+)="\\"([^"]+)\\""', cookie_string)
        if match:
            cookie_name = match.group(1)
            cookie_value = match.group(2)
            clean_cookie = f'{cookie_name}="{cookie_value}"'
            clean_cookie = clean_cookie + ";scratchcsrftoken=" + csrf_token
        head = {
            "Cookie": clean_cookie,
            "referer": "https://scratch.mit.edu/",
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRFToken": csrf_token,
            "Content-Type": "application/json",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Origin": "https://scratch.mit.edu",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept": "*/*",
        }
        return {"success": True, "cookie": head}
    else:
        data = respo.json()
        return {"success": False, "msg": data[0].get("msg")}


def isbanned(cookie):
    resp = requests.get("https://scratch.mit.edu/session/", headers=cookie)
    r = resp.json()
    return r["user"]["banned"]


def getrights(cookie, studio):
    resp = requests.get("https://scratch.mit.edu/session/", headers=cookie)
    r = resp.json()
    resp = requests.get(
        f"https://api.scratch.mit.edu/studios/{str(studio)}/users/{r['user']['username']}",
        headers={"X-Token": r['user']['token']}
    )
    r = resp.json()
    if r.get("manager"):
        return "manager"
    elif r.get("curator"):
        return "curator"
    elif r.get("invited"):
        return "invited"
    else:
        return "-"


def removeuser(cookie, studio, user):
    resp = requests.put(
        f"https://scratch.mit.edu/site-api/users/curators-in/{str(studio)}/remove/?usernames={user}",
        headers=cookie
    )
    return resp.status_code == 200


def removecurators(cookie, studio):
    loop = True
    while loop:
        req = requests.get(f"https://api.scratch.mit.edu/studios/{str(studio)}/curators?limit=40")
        curators = req.json()
        if len(curators) < 40:
            loop = False
        for curator in curators:
            if not removeuser(cookie, studio, curator["username"]):
                log(f"Произошла ошибка при удалении {curator['username']}")
            time.sleep(0.5)


def closeprojects(cookie, studio):
    resp = requests.put(
        f"https://scratch.mit.edu/site-api/galleries/{str(studio)}/mark/closed/",
        headers=cookie
    )
    return resp.status_code == 200


def removeprojects(cookie, studio):
    resp = requests.get("https://scratch.mit.edu/session/", headers=cookie)
    r = resp.json()
    token = r["user"]["token"]
    loop = True
    while loop:
        a = requests.get(f"https://api.scratch.mit.edu/studios/{studio}/projects/?limit=40")
        projects = a.json()
        l = len(projects)
        for p in projects:
            r = requests.delete(
                f"https://api.scratch.mit.edu/studios/{studio}/project/{p.get('id')}/",
                headers={"X-Token": token}
            )
            if r.status_code not in (200, 204):
                log(f"Ошибка {str(r.status_code)} при удалении проекта")
                time.sleep(10)
            else:
                time.sleep(0.1)
        if l < 40:
            loop = False


def acceptinvite(cookie, studio):
    resp = requests.get("https://scratch.mit.edu/session/", headers=cookie)
    r = resp.json()
    resp = requests.put(
        f"https://scratch.mit.edu/site-api/users/curators-in/{str(studio)}/add/?usernames={r['user']['username']}",
        headers=cookie
    )
    return resp.status_code == 200


def removemanagers(cookie, studio):
    req = requests.get(f"https://api.scratch.mit.edu/studios/{str(studio)}/managers?limit=40&offset=1")
    managers = req.json()
    ses = requests.get("https://scratch.mit.edu/session/", headers=cookie)
    r = ses.json()
    myusername = r["user"]["username"]
    for user in managers:
        if user["username"] != myusername:
            if not removeuser(cookie, studio, user["username"]):
                log(f"Произошла ошибка при удалении {user['username']}")
            time.sleep(0.5)


def cookie_to_string(cookie):
    c = SimpleCookie()
    c[cookie.name] = cookie.value
    morsel = c[cookie.name]
    if getattr(cookie, 'domain', None):
        morsel['domain'] = cookie.domain
    if getattr(cookie, 'path', None):
        morsel['path'] = cookie.path
    if getattr(cookie, 'secure', None):
        morsel['secure'] = True
    if getattr(cookie, 'httponly', None):
        morsel['httponly'] = True
    if hasattr(cookie, 'expires'):
        expires_date = datetime.now(UTC) + timedelta(weeks=2)
        morsel['expires'] = expires_date.strftime('%a, %d-%b-%Y %H:%M:%S GMT')
    if isinstance(getattr(cookie, 'expires', None), int):
        morsel['Max-Age'] = cookie.expires
    return morsel.OutputString()



def destroy_worker():
    window.progressBar.setValue(0)
    studio = int(re.findall(r'\d+', studiotextbox.get())[0])
    password = password_entry.get()
    username = username_entry.get()
    logged = login(username, password)
    cookie = logged["cookie"]
    log(f"Запуск... Удаляем студию {studio} с аккаунта {username}")
    if logged.get("success"):
        status = getrights(cookie, studio)
        if status == "manager":
            log("Отлично! Аккаунт - менеджер! Начинаем уничтожение")
            log("Удаляем менеджеров!")
            removemanagers(cookie, studio)                             #1
            window.progressBar.setValue(20)
            log("Удаляем кураторов!")
            removecurators(cookie, studio)                             #2
            window.progressBar.setValue(40)
            log("Закрываем доступ к проектам!")
            if not closeprojects(cookie, studio):                             #3
                log("Не удалось закрыть доступ к проектам, но ладно")
            window.progressBar.setValue(60)
            log("Удаляем проекты!")
            removeprojects(cookie, studio)                             #4
            window.progressBar.setValue(80)
            log("Проекты удалены!")
            if deletemyself.get() == 1:
                log("Удаляем себя!")
                removeuser(cookie, studio, username)                            #5
            window.progressBar.setValue(100)
            log("Готово!")
        elif status == "curator":
            log("Аккаунт - куратор! Удаляем проекты")
            removeprojects(cookie, studio)
            window.progressBar.setValue(50)
            if deletemyself.get() == 1:
                log("Удаляем себя!")
                removeuser(cookie, studio, username)
            window.progressBar.setValue(100)
            log("Готово")
        elif status == "invited":
            log("Аккаунт приглашён! Принимаем приглашение!")
            acceptinvite(cookie, studio)
            window.progressBar.setValue(50)
            log("Аккаунт теперь куратор! Удаляем проекты!")
            removeprojects(cookie, studio)
            window.progressBar.setValue(100)
            log("Проекты удалены!")
        else:
            log("Аккаунт не приглашён в студию :(")
    elif not logged.get("success"):
        log("Ошибка входа: " + logged.get("msg"))
        window.progressBar.setValue(100)
    elif isbanned(cookie):
        log("Акаунт забанен!")




def destroy():
    threading.Thread(target=destroy_worker, daemon=True).start()


class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi('gui.ui', self)

        self.setup_connections()
    
    def setup_connections(self):
        self.destroy_btn.clicked.connect(self.destroy)
        self.clear_logs_btn.triggered.connect(self.clear_logs)
        pass

    def destroy(self):
        is_checked = self.delete_myself_chbks.isChecked()
        if is_checked:
            deletemyself.set(1)
        else:
            deletemyself.set(0)
        
        username_entry.set(self.username_line.text())
        password_entry.set(self.password_line.text())
        studiotextbox.set(self.studio_line.text())
        destroy()
        
    
    def clear_logs(self):
        self.log.clear()

def main():
    global window
    app = QApplication(sys.argv)
    window = MyWindow()
    window.show()
    sys.exit(app.exec_())
    
    
class fake_tk_entry:
    def __init__(self):
        self.value = ""
    
    def get(self):
        return self.value
    
    def set(self, a):
        self.value = a
        
        
password_entry = fake_tk_entry()
username_entry = fake_tk_entry()
studiotextbox = fake_tk_entry()
deletemyself = fake_tk_entry()
deletemyself.set(1)

if __name__ == '__main__':
    main()


main()
