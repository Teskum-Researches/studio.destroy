import requests
import time
import re
import threading
from http.cookies import SimpleCookie
from datetime import datetime, timedelta, UTC
import sys

from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout, 
                            QLineEdit, QListWidget, QLabel, QProgressBar, 
                            QHBoxLayout, QCheckBox)

def log(message):
    window.logs.addItem(message)
    window.logs.scrollToBottom()

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
    global total_percents

    resp = requests.get("https://scratch.mit.edu/session/", headers=cookie)
    r = resp.json()
    resp = requests.get(
        f"https://api.scratch.mit.edu/studios/{str(studio)}/users/{r['user']['username']}",
        headers={"X-Token": r['user']['token']}
    )
    r = resp.json()
    projects = len(requests.get(f"https://api.scratch.mit.edu/studios/{str(studio)}/projects/?limit=40").json())
    if r.get("manager"):
        managers = len(requests.get(f"https://api.scratch.mit.edu/studios/{str(studio)}/managers?limit=40&offset=1").json())
        curators = len(requests.get(f"https://api.scratch.mit.edu/studios/{str(studio)}/curators?limit=40").json())
        projects = len(requests.get(f"https://api.scratch.mit.edu/studios/{str(studio)}/projects/?limit=40").json())
        total_percents = 100 / (projects + curators + managers)
        return "manager"
    elif r.get("curator"):
        projects = len(requests.get(f"https://api.scratch.mit.edu/studios/{str(studio)}/projects/?limit=40").json())
        total_percents = 100 / (projects)
        return "curator"
    elif r.get("invited"):
        projects = len(requests.get(f"https://api.scratch.mit.edu/studios/{str(studio)}/projects/?limit=40").json())
        total_percents = 100 / (projects)
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
            window.progress_bar.setValue(window.progress_bar.value() + round(total_percents))
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

            window.progress_bar.setValue(window.progress_bar.value() + round(total_percents))

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
            window.progress_bar.setValue(window.progress_bar.value() + round(total_percents))
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
    studio = int(re.findall(r'\d+', window.studio_input.text())[0])

    


    window.progress_bar.setValue(0)
    password = window.password_input.text()
    username = window.username_input.text()
    logged = login(username, password)
    cookie = logged.get('cookie')
    log(f"Запуск... Удаляем студию {studio} с аккаунта {username}")
    

    if logged.get("success"):
        status = getrights(cookie, studio)
        if status == "manager":
            log("Отлично! Аккаунт - менеджер! Начинаем уничтожение")
            log("Удаляем менеджеров!")
            removemanagers(cookie, studio)
            log("Удаляем кураторов!")
            removecurators(cookie, studio)
            window.progress_bar.setValue(40)
            log("Закрываем доступ к проектам!")
            if not closeprojects(cookie, studio):
                log("Не удалось закрыть доступ к проектам, но ладно")
            log("Удаляем проекты!")
            removeprojects(cookie, studio)
            log("Проекты удалены!")
            if window.delete_myself.isChecked():
                log("Удаляем себя!")
                removeuser(cookie, studio, username)
            log("Готово!")
        elif status == "curator":
            log("Аккаунт - куратор! Удаляем проекты")
            removeprojects(cookie, studio)
            if  window.delete_myself.isChecked():
                log("Удаляем себя!")
                removeuser(cookie, studio, username)
            log("Готово")
        elif status == "invited":
            log("Аккаунт приглашён! Принимаем приглашение!")
            acceptinvite(cookie, studio)
            log("Аккаунт теперь куратор! Удаляем проекты!")
            removeprojects(cookie, studio)
            log("Проекты удалены!")
        else:
            log("Аккаунта нету в студии, и он даже не приглашён :(")
    elif not logged.get("success"):
        log("Ошибка входа: " + logged.get("msg"))
    elif isbanned(cookie):
        log("Акаунт забанен!")




def destroy():
    threading.Thread(target=destroy_worker, daemon=True).start()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Studio.Destroy().v3')
        self.setGeometry(100, 100, 600, 480)
        self.setFixedSize(600, 480)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText('Ник')

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText('Пароль')
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.studio_input = QLineEdit()
        self.studio_input.setPlaceholderText('ID или ссылка студии')

        self.logs = QListWidget()
        self.copyright_label = QLabel("© 2025 Teskum Researches")
        self.delete_myself = QCheckBox("Удалить себя")

        self.destroy_btn = QPushButton('Уничтожить')
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        # Layout для кнопок
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.destroy_btn)

        # Layout для данных акаунта

        data_layout = QHBoxLayout()
        data_layout.addWidget(self.username_input)
        data_layout.addWidget(self.password_input)

        layout = QVBoxLayout()
        layout.addLayout(data_layout)
        layout.addWidget(self.studio_input)
        layout.addLayout(button_layout)
        layout.addWidget(self.logs)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.delete_myself)
        layout.addWidget(self.copyright_label)
        
        

        self.setLayout(layout)
        self.destroy_btn.clicked.connect(destroy)

        self.setup_connections()
    
    def setup_connections(self):
        self.destroy_btn.clicked.connect(self.destroy)
        pass
        

def main():
    global window
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
    


if __name__ == '__main__':
    main()
