# -*- coding: utf-8 -*-
"""
HydRo POS  -  by HydRo OS
Eigene Kassen-App (Point of Sale) in Python / tkinter.

Start:          python hydro_pos.py
Exe erstellen:  pip install pyinstaller
                pyinstaller --onefile --windowed --name "HydRoPOS" hydro_pos.py

Optional (nur wenn gewünscht):
    pip install pillow            -> Produktbilder jeder Art (JPG, PNG ...)
    pip install pyserial          -> COM-Ports für USB-Scanner automatisch finden
    pip install opencv-python pyzbar -> Barcode per Webcam scannen
"""
import json
import os
import shutil
import sys
import uuid
import webbrowser
import random
import datetime as dt
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

APP_NAME = "HydRo POS"
MAKER = "HydRo OS"
BARCODE_URL = "https://barcode.tec-it.com/de"   # kostenloser Barcode-Generator
EMOJI_FONT = "Segoe UI Emoji"

THEMES = {
    "Dunkel": dict(bg="#101010", panel="#1b1b1b", fg="#f2f2f2", muted="#8d8d8d",
                   accent="#3b9cff", entry="#2a2a2a", ok="#2ecc71", bad="#e74c3c"),
    "Grau":   dict(bg="#2b2d31", panel="#383a40", fg="#f2f3f5", muted="#a0a3aa",
                   accent="#4aa3ff", entry="#232428", ok="#3ddc84", bad="#ff5c5c"),
    "Hell":   dict(bg="#f1f3f6", panel="#ffffff", fg="#1b1b1b", muted="#6b7280",
                   accent="#1f7ae0", entry="#e6e9ee", ok="#1e9e57", bad="#d33a3a"),
}


# ----------------------------------------------------------------- Hilfsfunktionen
def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def money(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def parse_num(s, default=None):
    try:
        return float(str(s).strip().replace(",", "."))
    except ValueError:
        return default


def blend(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def detect_serial_ports():
    ports = []
    try:
        from serial.tools import list_ports
        ports = [f"{p.device} - {p.description}" for p in list_ports.comports()]
    except Exception:
        pass
    return ["USB-Tastatur-Modus (Standard bei den meisten Scannern)"] + ports


def detect_cameras():
    cams = []
    try:
        import cv2
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap is not None and cap.isOpened():
                cams.append(f"Kamera {i + 1} (Index {i})")
            if cap is not None:
                cap.release()
    except Exception:
        pass
    return cams or ["Kamera 1 (Index 0)", "Kamera 2 (Index 1)", "Kamera 3 (Index 2)"]


# ----------------------------------------------------------------- Daten
class DB:
    CONFIG = os.path.join(app_dir(), "hydro_pos_config.json")
    DEFAULT_CFG = {
        "setup_done": False, "data_dir": app_dir(), "theme": "Dunkel", "pin": "",
        "scanner_mode": "Barcode-Scanner", "scanner_device": "", "camera_device": "",
        "card_device": "", "app_logo": "", "boot_logo": "",
    }

    def __init__(self):
        self.cfg = dict(self.DEFAULT_CFG)
        if os.path.exists(self.CONFIG):
            try:
                with open(self.CONFIG, encoding="utf-8") as f:
                    self.cfg.update(json.load(f))
            except Exception:
                pass
        if not os.path.isdir(self.cfg["data_dir"]):
            self.cfg["data_dir"] = app_dir()

    def save_cfg(self):
        with open(self.CONFIG, "w", encoding="utf-8") as f:
            json.dump(self.cfg, f, ensure_ascii=False, indent=2)

    def path(self, name):
        return os.path.join(self.cfg["data_dir"], name)

    def load(self, name, default):
        try:
            with open(self.path(name), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default

    def save(self, name, data):
        os.makedirs(self.cfg["data_dir"], exist_ok=True)
        with open(self.path(name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def import_image(self, src):
        """Kopiert ein Bild in den Datenordner und gibt den relativen Pfad zurück."""
        folder = os.path.join(self.cfg["data_dir"], "images")
        os.makedirs(folder, exist_ok=True)
        name = uuid.uuid4().hex[:10] + os.path.splitext(src)[1].lower()
        shutil.copy(src, os.path.join(folder, name))
        return os.path.join("images", name)

    def move_data(self, new_dir):
        old = self.cfg["data_dir"]
        if os.path.abspath(old) == os.path.abspath(new_dir):
            return
        os.makedirs(new_dir, exist_ok=True)
        for fn in ("profile.json", "products.json", "coupons.json", "sales.json"):
            if os.path.exists(os.path.join(old, fn)):
                shutil.copy(os.path.join(old, fn), os.path.join(new_dir, fn))
        if os.path.isdir(os.path.join(old, "images")):
            shutil.copytree(os.path.join(old, "images"), os.path.join(new_dir, "images"),
                            dirs_exist_ok=True)
        self.cfg["data_dir"] = new_dir
        self.save_cfg()


# ----------------------------------------------------------------- UI-Bausteine
class ScrollFrame(tk.Frame):
    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.cv = tk.Canvas(self, bg=bg, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.cv.yview)
        self.inner = tk.Frame(self.cv, bg=bg)
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.win = self.cv.create_window((0, 0), window=self.inner, anchor="nw")
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfig(self.win, width=e.width))
        self.cv.configure(yscrollcommand=sb.set)
        self.cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.cv.bind("<Enter>", lambda e: self.cv.bind_all("<MouseWheel>", self._wheel))
        self.cv.bind("<Leave>", lambda e: self.cv.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        self.cv.yview_scroll(int(-e.delta / 120), "units")


class LoadingScreen(tk.Frame):
    """Ladescreen: Einkaufswagen fährt statt eines Punktes die Linie entlang."""

    def __init__(self, app, title, duration_ms, on_done, byline=False, fade=False):
        t = app.t
        super().__init__(app.container, bg=t["bg"])
        self.app, self.t, self.on_done, self.fade = app, t, on_done, fade
        self.duration, self.elapsed = duration_ms, 0
        self.cv = tk.Canvas(self, bg=t["bg"], highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.logo_img = app.load_logo(app.db.cfg["boot_logo"] or app.db.cfg["app_logo"], (140, 140))
        self.logo = self.cv.create_image(0, 0, image=self.logo_img) if self.logo_img else None
        self.title = self.cv.create_text(0, 0, text=title, fill=t["accent"],
                                         font=("Segoe UI", 34, "bold"), justify="center")
        self.track = self.cv.create_line(0, 0, 0, 0, width=8, fill=t["entry"], capstyle="round")
        self.prog = self.cv.create_line(0, 0, 0, 0, width=8, fill=t["accent"], capstyle="round")
        self.cart = self.cv.create_text(0, 0, text="🛒", font=(EMOJI_FONT, 36), fill=t["fg"])
        self.pct = self.cv.create_text(0, 0, text="0 %", fill=t["muted"], font=("Segoe UI", 12))
        self.by = (self.cv.create_text(0, 0, text=f"by: {MAKER}", fill=t["muted"],
                                       font=("Segoe UI", 11), anchor="se") if byline else None)
        self.after(50, self.tick)

    def layout(self):
        w, h = self.cv.winfo_width(), self.cv.winfo_height()
        self.x0, self.x1, self.y = w * 0.2, w * 0.8, h * 0.62
        if self.logo:
            self.cv.coords(self.logo, w / 2, h * 0.17)
        self.cv.coords(self.title, w / 2, h * 0.38 if self.logo else h * 0.3)
        self.cv.coords(self.track, self.x0, self.y, self.x1, self.y)
        self.cv.coords(self.pct, w / 2, self.y + 50)
        if self.by:
            self.cv.coords(self.by, w - 16, h - 12)

    def tick(self):
        self.layout()
        self.elapsed += 30
        p = min(self.elapsed / self.duration, 1.0)
        e = p * p * (3 - 2 * p) * 0.35 + p * 0.65          # leicht weiche Bewegung
        x = self.x0 + (self.x1 - self.x0) * e
        self.cv.coords(self.prog, self.x0, self.y, max(x, self.x0 + 1), self.y)
        self.cv.coords(self.cart, x, self.y - 30)
        self.cv.itemconfig(self.pct, text=f"{int(e * 100)} %")
        if p < 1.0:
            self.after(30, self.tick)
        elif self.fade:
            self.fade_step(0)
        else:
            self.after(250, self.on_done)

    def fade_step(self, i):
        s = i / 15
        t = self.t
        for item, col in ((self.title, t["accent"]), (self.prog, t["accent"]), (self.track, t["entry"]),
                          (self.cart, t["fg"]), (self.pct, t["muted"])):
            self.cv.itemconfig(item, fill=blend(col, t["bg"], s))
        if i < 15:
            self.after(40, lambda: self.fade_step(i + 1))
        else:
            self.on_done()


class SwipeScreen(tk.Frame):
    """'Bitte wische den Einkaufswagen nach rechts, um zu entsperren'"""

    X0, X1, Y = 70, 590, 60

    def __init__(self, app, on_unlock):
        t = app.t
        super().__init__(app.container, bg=t["bg"])
        self.t, self.on_unlock, self.drag = t, on_unlock, False
        logo = app.load_logo(app.db.cfg["app_logo"], (140, 140))
        if logo:
            self._logo = logo
            tk.Label(self, image=logo, bg=t["bg"]).pack(pady=(40, 0))
        tk.Label(self, text=f"Willkommen bei {APP_NAME}", bg=t["bg"], fg=t["accent"],
                 font=("Segoe UI", 34, "bold")).pack(pady=(60 if not logo else 20, 10))
        self.hint = tk.Label(self, text="Bitte wische den Einkaufswagen nach rechts, um zu entsperren",
                             bg=t["bg"], fg=t["muted"], font=("Segoe UI", 15))
        self.hint.pack(expand=True)
        self.cv = tk.Canvas(self, width=660, height=120, bg=t["bg"], highlightthickness=0)
        self.cv.pack(side="bottom", pady=60)
        self.cv.create_line(self.X0, self.Y, self.X1, self.Y, width=10, fill=t["entry"], capstyle="round")
        self.fill = self.cv.create_line(self.X0, self.Y, self.X0, self.Y, width=10,
                                        fill=t["accent"], capstyle="round")
        self.cv.create_text(self.X1 + 40, self.Y, text="🔓", font=(EMOJI_FONT, 26), fill=t["muted"])
        self.cart = self.cv.create_text(self.X0, self.Y - 4, text="🛒", font=(EMOJI_FONT, 36), fill=t["fg"])
        self.cx = self.X0
        self.cv.bind("<ButtonPress-1>", self.press)
        self.cv.bind("<B1-Motion>", self.motion)
        self.cv.bind("<ButtonRelease-1>", self.release)

    def press(self, e):
        self.drag = abs(e.x - self.cx) < 45

    def move(self, x):
        self.cx = min(max(x, self.X0), self.X1)
        self.cv.coords(self.cart, self.cx, self.Y - 4)
        self.cv.coords(self.fill, self.X0, self.Y, self.cx, self.Y)

    def motion(self, e):
        if self.drag:
            self.move(e.x)

    def release(self, e):
        if not self.drag:
            return
        self.drag = False
        if self.cx >= self.X1 - 15:
            self.on_unlock()
        else:
            self.snap_back()

    def snap_back(self):
        if self.cx > self.X0 + 4:
            self.move(self.cx - max(8, (self.cx - self.X0) * 0.2))
            self.after(15, self.snap_back)
        else:
            self.move(self.X0)


# ----------------------------------------------------------------- Haupt-App
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME}  -  by {MAKER}")
        self.geometry("1200x760")
        self.minsize(1000, 660)
        self.db = DB()
        self._imgs = {}
        self.apply_theme()
        self.container = tk.Frame(self, bg=self.t["bg"])
        self.container.pack(fill="both", expand=True)
        self.start()

    # ---- Theme / Widgets
    def apply_theme(self):
        self.t = THEMES.get(self.db.cfg["theme"], THEMES["Dunkel"])
        t = self.t
        self.configure(bg=t["bg"])
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure("Treeview", background=t["panel"], fieldbackground=t["panel"], foreground=t["fg"],
                     rowheight=30, borderwidth=0, font=("Segoe UI", 11))
        st.configure("Treeview.Heading", background=t["entry"], foreground=t["fg"],
                     font=("Segoe UI", 11, "bold"), borderwidth=0)
        st.map("Treeview", background=[("selected", t["accent"])], foreground=[("selected", "#ffffff")])
        st.configure("TCombobox", fieldbackground=t["entry"], background=t["entry"],
                     foreground=t["fg"], arrowcolor=t["fg"], font=("Segoe UI", 11))
        st.configure("Vertical.TScrollbar", background=t["entry"], troughcolor=t["bg"], arrowcolor=t["fg"])
        self.option_add("*TCombobox*Listbox.background", t["entry"])
        self.option_add("*TCombobox*Listbox.foreground", t["fg"])

    def lbl(self, parent, text, size=11, bold=False, color=None, **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", parent["bg"]), fg=color or self.t["fg"],
                        font=("Segoe UI", size, "bold" if bold else "normal"), **kw)

    def btn(self, parent, text, cmd, kind="accent", **kw):
        colors = {"accent": (self.t["accent"], "#ffffff"), "ok": (self.t["ok"], "#ffffff"),
                  "bad": (self.t["bad"], "#ffffff"), "flat": (self.t["entry"], self.t["fg"])}
        bg, fg = colors[kind]
        return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=blend(bg, "#ffffff", .2),
                         activeforeground=fg, relief="flat", bd=0, padx=kw.pop("padx", 16),
                         pady=kw.pop("pady", 8), font=kw.pop("font", ("Segoe UI", 11, "bold")),
                         cursor="hand2", **kw)

    def entry(self, parent, var=None, width=28, **kw):
        return tk.Entry(parent, textvariable=var, width=width, bg=self.t["entry"], fg=self.t["fg"],
                        insertbackground=self.t["fg"], relief="flat", font=("Segoe UI", 12),
                        highlightthickness=1, highlightbackground=self.t["entry"],
                        highlightcolor=self.t["accent"], **kw)

    def dialog(self, title, w, h):
        d = tk.Toplevel(self)
        d.title(title)
        d.configure(bg=self.t["bg"])
        d.geometry(f"{w}x{h}+{self.winfo_x() + 120}+{self.winfo_y() + 80}")
        d.transient(self)
        d.grab_set()
        return d

    def path_of(self, rel):
        if not rel:
            return ""
        return rel if os.path.isabs(rel) else os.path.join(self.db.cfg["data_dir"], rel)

    def load_img(self, path, size):
        key = (path, size)
        if key in self._imgs:
            return self._imgs[key]
        img = None
        try:
            if HAS_PIL:
                im = Image.open(path)
                im.thumbnail(size)
                img = ImageTk.PhotoImage(im)
            else:
                p = tk.PhotoImage(file=path)
                f = max(1, p.width() // size[0], p.height() // size[1])
                img = p.subsample(f) if f > 1 else p
        except Exception:
            img = None
        self._imgs[key] = img
        return img

    def load_logo(self, path, size):
        if not path or not os.path.exists(path):
            return None
        return self.load_img(path, size)

    def show(self, frame):
        for w in self.container.winfo_children():
            if w is not frame:
                w.destroy()
        frame.pack(fill="both", expand=True)

    # ---- Start-Ablauf
    def start(self):
        if not self.db.cfg["setup_done"]:
            self.show(LoadingScreen(self, f"Willkommen bei {APP_NAME}", 5000,
                                    self.show_swipe, fade=True))
        else:
            profile = self.db.load("profile.json", {})
            name = profile.get("store", APP_NAME)
            self.show(LoadingScreen(self, name, 6000, self.show_pin_or_welcome, byline=True))

    def show_swipe(self):
        self.show(SwipeScreen(self, self.show_setup))

    # ---- Ersteinrichtung
    def show_setup(self):
        t = self.t
        f = tk.Frame(self.container, bg=t["bg"])
        self.show(f)
        self.lbl(f, f"Willkommen bei {APP_NAME}", 28, True, t["accent"]).pack(pady=(24, 2))
        self.lbl(f, "Bitte gib deine Infos ein", 13, color=t["muted"]).pack(pady=(0, 10))
        sf = ScrollFrame(f, t["bg"])
        sf.pack(fill="both", expand=True, padx=120)
        box = sf.inner
        v = {k: tk.StringVar() for k in
             ("first", "last", "phone", "email", "store", "address", "pin")}
        rows = [("Name", "first"), ("Nachname", "last"), ("Telefonnummer", "phone"),
                ("E-Mail", "email"), ("Name des Stores", "store"), ("Adresse", "address"),
                ("PIN zum Starten (optional, Zahlen)", "pin")]
        for i, (txt, key) in enumerate(rows):
            self.lbl(box, txt, 11, color=t["muted"]).grid(row=i, column=0, sticky="w", pady=6, padx=(0, 20))
            self.entry(box, v[key], 36, show="•" if key == "pin" else "").grid(row=i, column=1, sticky="we", pady=6)
        box.columnconfigure(1, weight=1)

        r = len(rows)
        self.lbl(box, "Barcode-Eingabe", 14, True).grid(row=r, column=0, columnspan=2, sticky="w", pady=(24, 4))
        mode = tk.StringVar(value="Barcode-Scanner")
        mf = tk.Frame(box, bg=t["bg"])
        mf.grid(row=r + 1, column=0, columnspan=2, sticky="w")
        combo = ttk.Combobox(box, state="readonly", width=60)

        def refresh_devices(*_):
            if mode.get() == "Barcode-Scanner":
                combo["values"] = detect_serial_ports()
            else:
                combo["values"] = detect_cameras()
            combo.current(0)
            dev_lbl.config(text="USB-Anschluss des Scanners:" if mode.get() == "Barcode-Scanner"
                           else "Webcam auswählen:")

        for txt in ("Barcode-Scanner", "Kamera"):
            tk.Radiobutton(mf, text=txt, variable=mode, value=txt, command=refresh_devices,
                           bg=t["bg"], fg=t["fg"], selectcolor=t["entry"], activebackground=t["bg"],
                           activeforeground=t["fg"], font=("Segoe UI", 11)).pack(side="left", padx=(0, 20))
        dev_lbl = self.lbl(box, "", 11, color=t["muted"])
        dev_lbl.grid(row=r + 2, column=0, sticky="w", pady=8)
        combo.grid(row=r + 2, column=1, sticky="w")
        refresh_devices()

        link = tk.Label(box, text="Kostenlos Barcodes zu Zahlen/Produkten erstellen: " + BARCODE_URL,
                        bg=t["bg"], fg=t["accent"], cursor="hand2", font=("Segoe UI", 11, "underline"))
        link.grid(row=r + 3, column=0, columnspan=2, sticky="w", pady=(18, 30))
        link.bind("<Button-1>", lambda e: webbrowser.open(BARCODE_URL))

        def finish():
            if not v["store"].get().strip():
                messagebox.showwarning(APP_NAME, "Bitte gib den Namen deines Stores ein.")
                return
            pin = v["pin"].get().strip()
            if pin and not pin.isdigit():
                messagebox.showwarning(APP_NAME, "Die PIN darf nur aus Zahlen bestehen.")
                return
            self.db.save("profile.json", {k: v[k].get().strip() for k in v if k != "pin"})
            c = self.db.cfg
            c.update(setup_done=True, pin=pin, scanner_mode=mode.get())
            c["scanner_device" if mode.get() == "Barcode-Scanner" else "camera_device"] = combo.get()
            self.db.save_cfg()
            self.show_thanks()

        self.btn(f, "Fertig", finish, "ok", font=("Segoe UI", 13, "bold"), padx=40).pack(pady=14)

    def show_thanks(self):
        f = tk.Frame(self.container, bg=self.t["bg"])
        self.show(f)
        self.lbl(f, "Danke fürs Anmelden\nund für Ihre Zeit.", 30, True, self.t["accent"],
                 justify="center").pack(expand=True)
        self.after(2500, self.show_main)

    # ---- PIN / Willkommen
    def show_pin_or_welcome(self):
        if self.db.cfg["pin"]:
            self.show_pin()
        else:
            self.show_welcome_back()

    def show_pin(self):
        t = self.t
        f = tk.Frame(self.container, bg=t["bg"])
        self.show(f)
        logo = self.load_logo(self.db.cfg["app_logo"], (110, 110))
        if logo:
            f._logo = logo
            tk.Label(f, image=logo, bg=t["bg"]).pack(pady=(30, 0))
        self.lbl(f, "PIN eingeben", 26, True, t["accent"]).pack(pady=(30, 8))
        dots = self.lbl(f, "", 30, color=t["fg"])
        dots.pack(pady=6)
        msg = self.lbl(f, " ", 12, color=t["bad"])
        msg.pack()
        buf = []

        def update():
            dots.config(text="●  " * len(buf) + "○  " * max(0, 4 - len(buf)))

        def press(d):
            if d == "⌫":
                if buf:
                    buf.pop()
            elif d == "C":
                buf.clear()
            else:
                buf.append(d)
            msg.config(text=" ")
            update()
            if "".join(buf) == self.db.cfg["pin"]:
                self.show_welcome_back()
            elif len(buf) >= max(len(self.db.cfg["pin"]), 4) and d not in ("⌫", "C"):
                msg.config(text="Falsche PIN")
                buf.clear()
                update()

        pad = tk.Frame(f, bg=t["bg"])
        pad.pack(pady=14)
        for i, d in enumerate("123456789C0⌫"):
            b = tk.Button(pad, text=d, width=4, height=1, command=lambda x=d: press(x), relief="flat",
                          bg=t["panel"], fg=t["fg"], activebackground=t["accent"], activeforeground="#fff",
                          font=("Segoe UI", 22, "bold"), cursor="hand2")
            b.grid(row=i // 3, column=i % 3, padx=8, pady=8, ipadx=10, ipady=6)
        update()

    def show_welcome_back(self):
        f = tk.Frame(self.container, bg=self.t["bg"])
        self.show(f)
        self.lbl(f, "Willkommen", 34, True, self.t["accent"]).pack(expand=True, pady=(0, 0))
        self.lbl(f, "Ihre Daten wurden bereits geladen.", 15, color=self.t["muted"]).pack(expand=True)
        self.after(1800, self.show_main)

    # ---- Hauptfenster
    def show_main(self, view="sale"):
        t = self.t
        self.apply_theme()
        main = tk.Frame(self.container, bg=t["bg"])
        self.show(main)
        profile = self.db.load("profile.json", {})
        self.store_name = profile.get("store", APP_NAME)
        bar = tk.Frame(main, bg=t["panel"], height=58)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        menu_btn = tk.Button(bar, text="☰", font=("Segoe UI", 20), bg=t["panel"], fg=t["fg"], relief="flat",
                             activebackground=t["entry"], activeforeground=t["fg"], cursor="hand2", bd=0, padx=16)
        menu_btn.pack(side="left", fill="y")
        logo = self.load_logo(self.db.cfg["app_logo"], (36, 36))
        if logo:
            bar._logo = logo
            tk.Label(bar, image=logo, bg=t["panel"]).pack(side="left", padx=(4, 6))
        self.lbl(bar, self.store_name, 17, True, t["accent"]).pack(side="left", padx=6)
        self.mode_lbl = self.lbl(bar, "", 11, color=t["muted"])
        self.mode_lbl.pack(side="left", padx=14)
        clock = self.lbl(bar, "", 12, color=t["muted"])
        clock.pack(side="right", padx=18)

        def tick():
            clock.config(text=dt.datetime.now().strftime("%d.%m.%Y  %H:%M:%S"))
            clock.after(1000, tick)
        tick()

        menu = tk.Menu(self, tearoff=0, bg=t["panel"], fg=t["fg"], activebackground=t["accent"],
                       activeforeground="#fff", font=("Segoe UI", 12), bd=0)
        for txt, key in (("🛒  Verkaufsmodus", "sale"), ("🛠  Developer-Modus", "dev"),
                         ("🏷  Rabattcodes", "coupons"), ("📈  Gewinn / Verlust", "profit"),
                         ("⚙  Einstellungen", "settings")):
            menu.add_command(label=txt, command=lambda k=key: self.switch_view(k))
        menu_btn.config(command=lambda: menu.tk_popup(menu_btn.winfo_rootx(),
                                                      menu_btn.winfo_rooty() + menu_btn.winfo_height()))
        self.body = tk.Frame(main, bg=t["bg"])
        self.body.pack(fill="both", expand=True)
        self.switch_view(view)

    def switch_view(self, key):
        for w in self.body.winfo_children():
            w.destroy()
        names = {"sale": "Verkaufsmodus", "dev": "Developer-Modus", "coupons": "Rabattcodes",
                 "profit": "Gewinn / Verlust", "settings": "Einstellungen"}
        self.mode_lbl.config(text=names[key])
        getattr(self, "view_" + key)()

    # ---- Daten-Helfer
    def products(self):
        return self.db.load("products.json", [])

    def coupons(self):
        return self.db.load("coupons.json", [])

    def sales(self):
        return self.db.load("sales.json", [])

    # ================================================================ VERKAUFSMODUS
    def view_sale(self):
        t, body = self.t, self.body
        self.cart, self.applied = {}, None
        prods = self.products()
        by_id = {p["id"]: p for p in prods}

        left = tk.Frame(body, bg=t["bg"])
        left.pack(side="left", fill="both", expand=True, padx=(12, 6), pady=12)
        right = tk.Frame(body, bg=t["panel"], width=440)
        right.pack(side="right", fill="y", padx=(6, 12), pady=12)
        right.pack_propagate(False)

        top = tk.Frame(left, bg=t["bg"])
        top.pack(fill="x")
        self.lbl(top, "🔍 Suche", 11, color=t["muted"]).grid(row=0, column=0, sticky="w")
        self.lbl(top, "▌▌ Barcode / Zahlen", 11, color=t["muted"]).grid(row=0, column=1, sticky="w", padx=14)
        search, code = tk.StringVar(), tk.StringVar()
        se = self.entry(top, search, 26)
        se.grid(row=1, column=0, pady=4)
        ce = self.entry(top, code, 26)
        ce.grid(row=1, column=1, padx=14, pady=4)
        status = self.lbl(top, " ", 11, color=t["muted"])
        status.grid(row=2, column=0, columnspan=3, sticky="w")
        self.btn(top, "📷 Kamera", lambda: scan_cam(), "flat").grid(row=1, column=2)

        grid_host = ScrollFrame(left, t["bg"])
        grid_host.pack(fill="both", expand=True, pady=(8, 0))

        def fill_grid(*_):
            for w in grid_host.inner.winfo_children():
                w.destroy()
            q = search.get().strip().lower()
            shown = [p for p in prods if q in p["name"].lower() or q in p.get("barcode", "")]
            for i, p in enumerate(shown):
                card = tk.Frame(grid_host.inner, bg=t["panel"], width=150, height=170, cursor="hand2")
                card.grid(row=i // 4, column=i % 4, padx=6, pady=6)
                card.pack_propagate(False)
                img = self.load_img(self.path_of(p.get("image")), (96, 80)) if p.get("image") else None
                il = tk.Label(card, image=img, text="" if img else "🛍", font=(EMOJI_FONT, 34),
                              bg=t["panel"], fg=t["muted"])
                il.image = img
                il.pack(pady=(10, 4))
                n = self.lbl(card, p["name"], 11, True, wraplength=130)
                n.pack()
                pr = self.lbl(card, money(p["price"]), 11, color=t["accent"])
                pr.pack()
                for w in (card, il, n, pr):
                    w.bind("<Button-1>", lambda e, pid=p["id"]: add(pid))
            if not shown:
                self.lbl(grid_host.inner, "Keine Produkte. Im Developer-Modus anlegen.",
                         12, color=t["muted"]).grid(pady=30, padx=20)

        search.trace_add("write", fill_grid)

        # Warenkorb
        self.lbl(right, "Warenkorb", 16, True, bg=t["panel"]).pack(anchor="w", padx=14, pady=(12, 4))
        tree = ttk.Treeview(right, columns=("n", "q", "s"), show="headings", height=10)
        for c, txt, w in (("n", "Artikel", 190), ("q", "Menge", 60), ("s", "Summe", 100)):
            tree.heading(c, text=txt)
            tree.column(c, width=w, anchor="w" if c == "n" else "e")
        tree.pack(fill="x", padx=14)
        bf = tk.Frame(right, bg=t["panel"])
        bf.pack(fill="x", padx=14, pady=6)
        sums = tk.Frame(right, bg=t["panel"])
        cf = tk.Frame(right, bg=t["panel"])
        cf.pack(fill="x", padx=14, pady=(6, 0))
        self.lbl(cf, "Rabatt-/Gutscheincode", 10, color=t["muted"], bg=t["panel"]).pack(anchor="w")
        cvar = tk.StringVar()
        self.entry(cf, cvar, 18).pack(side="left")
        cinfo = self.lbl(right, " ", 11, color=t["ok"], bg=t["panel"], wraplength=400, justify="left")
        sums.pack(fill="x", padx=14, pady=(10, 0))
        subl = self.lbl(sums, "", 12, color=t["muted"], bg=t["panel"])
        subl.pack(anchor="e")
        disl = self.lbl(sums, "", 12, color=t["ok"], bg=t["panel"])
        disl.pack(anchor="e")
        totl = self.lbl(sums, "", 24, True, bg=t["panel"])
        totl.pack(anchor="e", pady=(4, 0))

        def calc():
            sub = sum(by_id[pid]["price"] * q for pid, q in self.cart.items() if pid in by_id)
            pct = self.applied["percent"] if self.applied else 0
            disc = sub * pct / 100
            return sub, disc, sub - disc

        def refresh():
            tree.delete(*tree.get_children())
            for pid, q in self.cart.items():
                p = by_id[pid]
                tree.insert("", "end", iid=pid, values=(p["name"], q, money(p["price"] * q)))
            sub, disc, tot = calc()
            subl.config(text=f"Zwischensumme: {money(sub)}")
            disl.config(text=f"Rabatt ({self.applied['percent']:g}%): -{money(disc)}" if self.applied else " ")
            totl.config(text=f"Gesamt: {money(tot)}")

        def add(pid, n=1):
            self.cart[pid] = self.cart.get(pid, 0) + n
            if self.cart[pid] <= 0:
                del self.cart[pid]
            refresh()

        def sel_change(n):
            s = tree.selection()
            if s:
                add(s[0], n)
                if s[0] in self.cart:
                    tree.selection_set(s[0])

        def remove():
            s = tree.selection()
            if s:
                self.cart.pop(s[0], None)
                refresh()

        def clear():
            self.cart.clear()
            refresh()

        for txt, cmd, kind in (("＋", lambda: sel_change(1), "flat"), ("－", lambda: sel_change(-1), "flat"),
                               ("Entfernen", remove, "flat"), ("Leeren", clear, "bad")):
            self.btn(bf, txt, cmd, kind, padx=12, pady=5).pack(side="left", padx=(0, 6))

        def apply_code(raw=None):
            c = (raw if raw is not None else cvar.get()).strip()
            if not c:
                return False
            for cp in self.coupons():
                if cp["code"] == c and cp.get("left", 0) > 0:
                    self.applied = cp
                    cinfo.config(text=f"✔ Der Kunde hat jetzt {cp['percent']:g}% Rabatt bekommen.",
                                 fg=t["ok"])
                    cvar.set("")
                    refresh()
                    return True
            cinfo.config(text="✖ Code ungültig oder aufgebraucht.", fg=t["bad"])
            return False

        self.btn(cf, "Einlösen", apply_code, "flat", padx=12, pady=5).pack(side="left", padx=6)
        cinfo.pack(fill="x", padx=14, anchor="w")

        # Barcode: Scanner tippt Zahlen + Enter
        def on_barcode(_=None):
            c = code.get().strip()
            code.set("")
            if not c:
                return
            for p in prods:
                if p.get("barcode") == c:
                    add(p["id"])
                    status.config(text=f"✔ {p['name']} hinzugefügt", fg=t["ok"])
                    return
            status.config(text=f"✖ Barcode {c} nicht gefunden", fg=t["bad"])

        ce.bind("<Return>", on_barcode)

        def scan_cam():
            res = self.camera_scan()
            if res:
                code.set(res)
                on_barcode()

        def checkout():
            if not self.cart:
                messagebox.showinfo(APP_NAME, "Der Warenkorb ist leer.")
                return
            self.pay_dialog(by_id, calc, apply_code_dialog, lambda: (self.cart.clear(), setattr(self, "applied", None),
                                                                      cinfo.config(text=" "), refresh()),
                            lambda: self.applied)

        def apply_code_dialog(c):
            ok = apply_code(c)
            return ok

        self.btn(right, "Kauf abschließen", checkout, "ok", font=("Segoe UI", 15, "bold"),
                 pady=12).pack(side="bottom", anchor="e", padx=14, pady=14)
        fill_grid()
        refresh()
        ce.focus_set()

    def camera_scan(self):
        try:
            import cv2
            from pyzbar import pyzbar
        except ImportError:
            messagebox.showinfo(APP_NAME, "Für den Kamera-Scan bitte installieren:\n\n"
                                          "pip install opencv-python pyzbar")
            return None
        idx = 0
        dev = self.db.cfg.get("camera_device", "")
        if "Index" in dev:
            try:
                idx = int(dev.split("Index")[1].strip(" )"))
            except ValueError:
                pass
        cap = cv2.VideoCapture(idx)
        found, end = None, dt.datetime.now() + dt.timedelta(seconds=20)
        while dt.datetime.now() < end and not found:
            ok, frame = cap.read()
            if not ok:
                break
            codes = pyzbar.decode(frame)
            if codes:
                found = codes[0].data.decode("utf-8")
            cv2.imshow("Barcode scannen (ESC = Abbrechen)", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break
        cap.release()
        cv2.destroyAllWindows()
        return found

    def pay_dialog(self, by_id, calc, apply_code, on_done, get_applied):
        t = self.t
        d = self.dialog("Kauf abschließen", 520, 480)
        top = tk.Frame(d, bg=t["bg"])
        top.pack(fill="both", expand=True, padx=24, pady=20)
        total_lbl = self.lbl(top, "", 26, True, t["accent"])
        total_lbl.pack(pady=(0, 14))
        info = self.lbl(top, " ", 11, color=t["ok"])
        info.pack()
        area = tk.Frame(top, bg=t["bg"])
        area.pack(fill="both", expand=True, pady=10)

        def refresh_total():
            total_lbl.config(text=f"Zu zahlen: {money(calc()[2])}")
            a = get_applied()
            info.config(text=f"Rabatt {a['percent']:g}% aktiv" if a else " ")

        def clear_area():
            for w in area.winfo_children():
                w.destroy()

        def choose():
            clear_area()
            refresh_total()
            self.lbl(area, "Wie möchte der Kunde zahlen?", 12, color=t["muted"]).pack(pady=(0, 12))
            self.btn(area, "🎟  Gutschein einfügen", voucher, "flat", pady=12).pack(fill="x", pady=5)
            self.btn(area, "💶  Bar", cash, "flat", pady=12).pack(fill="x", pady=5)
            dev = self.db.cfg.get("card_device", "")
            self.btn(area, "💳  Karte" + (f"  ({dev})" if dev else ""), card, "flat", pady=12).pack(fill="x", pady=5)

        def voucher():
            clear_area()
            self.lbl(area, "Gutscheincode (Freirubbel-Code) eingeben:", 12, color=t["muted"]).pack(pady=(0, 8))
            v = tk.StringVar()
            e = self.entry(area, v, 20)
            e.pack(pady=4)
            e.focus_set()
            msg = self.lbl(area, " ", 11, color=t["bad"])
            msg.pack()

            def go(_=None):
                if apply_code(v.get()):
                    choose()
                else:
                    msg.config(text="Code ungültig oder aufgebraucht.")
            e.bind("<Return>", go)
            self.btn(area, "Gutschein einlösen", go, "accent").pack(pady=8)
            self.btn(area, "Zurück", choose, "flat").pack()

        def cash():
            clear_area()
            tot = calc()[2]
            self.lbl(area, "Bar - Gegeben (optional):", 12, color=t["muted"]).pack(pady=(0, 8))
            v = tk.StringVar()
            e = self.entry(area, v, 14)
            e.pack()
            e.focus_set()
            back = self.lbl(area, " ", 16, True, t["ok"])
            back.pack(pady=10)

            def upd(*_):
                g = parse_num(v.get())
                back.config(text=f"Rückgeld: {money(g - tot)}" if g is not None and g >= tot else " ")
            v.trace_add("write", upd)
            self.btn(area, "Zahlung bestätigen", lambda: finish("Bar"), "ok").pack(pady=6)
            self.btn(area, "Zurück", choose, "flat").pack()

        def card():
            clear_area()
            dev = self.db.cfg.get("card_device") or "Kartenterminal"
            self.lbl(area, f"Bitte {money(calc()[2])} am Gerät\n„{dev}“ bezahlen lassen.", 14,
                     justify="center").pack(pady=20)
            self.btn(area, "Zahlung erfolgreich", lambda: finish("Karte"), "ok").pack(pady=6)
            self.btn(area, "Zurück", choose, "flat").pack()

        def finish(method):
            sub, disc, tot = calc()
            a = get_applied()
            items, cost = [], 0.0
            prods = self.products()
            for pid, q in self.cart.items():
                p = by_id[pid]
                items.append(dict(name=p["name"], qty=q, price=p["price"], cost=p.get("cost", 0)))
                cost += p.get("cost", 0) * q
                for pp in prods:
                    if pp["id"] == pid and pp.get("stock") is not None:
                        pp["stock"] = max(0, pp["stock"] - q)
            self.db.save("products.json", prods)
            if a:
                cps = self.coupons()
                for cp in cps:
                    if cp["code"] == a["code"]:
                        cp["left"] = max(0, cp.get("left", 1) - 1)
                self.db.save("coupons.json", cps)
            sales = self.sales()
            sales.append(dict(id=uuid.uuid4().hex[:8], time=dt.datetime.now().isoformat(timespec="seconds"),
                              items=items, subtotal=sub, percent=a["percent"] if a else 0,
                              code=a["code"] if a else "", total=tot, cost=cost, method=method))
            self.db.save("sales.json", sales)
            clear_area()
            info.config(text=" ")
            self.lbl(area, "✔", 60, True, t["ok"]).pack(pady=(10, 0))
            self.lbl(area, "Kauf erfolgreich abgeschlossen", 15, True).pack(pady=8)
            self.btn(area, "Fertig", lambda: (d.destroy(), on_done()), "ok", padx=50).pack(pady=10)

        choose()

    # ================================================================ DEVELOPER-MODUS
    def view_dev(self):
        t, body = self.t, self.body
        head = tk.Frame(body, bg=t["bg"])
        head.pack(fill="x", padx=16, pady=(14, 6))
        self.lbl(head, "Produkte verwalten", 18, True).pack(side="left")
        cols = ("name", "price", "cost", "barcode", "stock")
        tree = ttk.Treeview(body, columns=cols, show="headings")
        for c, txt, w in (("name", "Produkt", 280), ("price", "Preis", 110), ("cost", "Einkauf", 110),
                          ("barcode", "Barcode", 200), ("stock", "Bestand", 90)):
            tree.heading(c, text=txt)
            tree.column(c, width=w, anchor="w")
        tree.pack(fill="both", expand=True, padx=16, pady=6)

        def fill():
            tree.delete(*tree.get_children())
            for p in self.products():
                tree.insert("", "end", iid=p["id"], values=(
                    p["name"], money(p["price"]), money(p.get("cost", 0)), p.get("barcode", ""),
                    "" if p.get("stock") is None else p["stock"]))

        def edit(new=False):
            if new:
                self.product_dialog(None, fill)
            else:
                s = tree.selection()
                if not s:
                    return messagebox.showinfo(APP_NAME, "Bitte erst ein Produkt auswählen.")
                self.product_dialog(next(p for p in self.products() if p["id"] == s[0]), fill)

        def delete():
            s = tree.selection()
            if s and messagebox.askyesno(APP_NAME, "Produkt wirklich löschen?"):
                self.db.save("products.json", [p for p in self.products() if p["id"] != s[0]])
                fill()

        bf = tk.Frame(body, bg=t["bg"])
        bf.pack(fill="x", padx=16, pady=(0, 14))
        self.btn(bf, "＋ Neues Produkt", lambda: edit(True), "ok").pack(side="left")
        self.btn(bf, "Bearbeiten", edit, "flat").pack(side="left", padx=8)
        self.btn(bf, "Löschen", delete, "bad").pack(side="left")
        link = tk.Label(bf, text="Barcodes kostenlos erstellen ↗", bg=t["bg"], fg=t["accent"], cursor="hand2",
                        font=("Segoe UI", 11, "underline"))
        link.pack(side="right")
        link.bind("<Button-1>", lambda e: webbrowser.open(BARCODE_URL))
        tree.bind("<Double-1>", lambda e: edit())
        fill()

    def product_dialog(self, p, on_save):
        t = self.t
        d = self.dialog("Produkt" + (" bearbeiten" if p else " hinzufügen"), 520, 560)
        p = p or {}
        v = dict(name=tk.StringVar(value=p.get("name", "")), price=tk.StringVar(value=str(p.get("price", ""))),
                 cost=tk.StringVar(value=str(p.get("cost", ""))), barcode=tk.StringVar(value=p.get("barcode", "")),
                 stock=tk.StringVar(value="" if p.get("stock") is None else str(p.get("stock"))))
        img = {"path": p.get("image", ""), "new": ""}
        f = tk.Frame(d, bg=t["bg"])
        f.pack(fill="both", expand=True, padx=24, pady=18)
        rows = [("Produktname", "name"), ("Verkaufspreis (€)", "price"), ("Einkaufspreis (€, für Gewinn)", "cost"),
                ("Barcode (einscannen oder tippen)", "barcode"), ("Bestand (leer = unbegrenzt)", "stock")]
        for i, (txt, k) in enumerate(rows):
            self.lbl(f, txt, 11, color=t["muted"]).grid(row=i, column=0, sticky="w", pady=7, padx=(0, 14))
            self.entry(f, v[k], 24).grid(row=i, column=1, sticky="we", pady=7)
        imglbl = self.lbl(f, "Kein Bild", 11, color=t["muted"])
        imglbl.grid(row=len(rows) + 1, column=0, columnspan=2, pady=8)

        def show_img():
            path = img["new"] or self.path_of(img["path"])
            im = self.load_img(path, (120, 100)) if path else None
            imglbl.config(image=im or "", text="" if im else "Kein Bild")
            imglbl.image = im
        show_img()

        def pick():
            fn = filedialog.askopenfilename(filetypes=[("Bilder", "*.png *.gif *.jpg *.jpeg"), ("Alle", "*.*")])
            if fn:
                img["new"] = fn
                show_img()
        self.btn(f, "🖼 Bild auswählen", pick, "flat").grid(row=len(rows), column=0, columnspan=2, pady=(10, 0))

        def save():
            name, price = v["name"].get().strip(), parse_num(v["price"].get())
            if not name or price is None:
                return messagebox.showwarning(APP_NAME, "Bitte Name und Preis angeben.", parent=d)
            bc = v["barcode"].get().strip()
            if bc and any(x.get("barcode") == bc and x["id"] != p.get("id") for x in self.products()):
                return messagebox.showwarning(APP_NAME, "Dieser Barcode ist schon vergeben.", parent=d)
            stock = v["stock"].get().strip()
            rec = dict(id=p.get("id") or uuid.uuid4().hex[:8], name=name, price=price,
                       cost=parse_num(v["cost"].get(), 0.0), barcode=bc,
                       stock=int(stock) if stock.isdigit() else None,
                       image=self.db.import_image(img["new"]) if img["new"] else img["path"])
            prods = [x for x in self.products() if x["id"] != rec["id"]] if p.get("id") else self.products()
            if p.get("id"):   # Reihenfolge behalten
                prods = [rec if x["id"] == p["id"] else x for x in self.products()]
            else:
                prods.append(rec)
            self.db.save("products.json", prods)
            d.destroy()
            on_save()
        self.btn(d, "Speichern", save, "ok", padx=40).pack(pady=(0, 18))

    # ================================================================ RABATTCODES
    def view_coupons(self):
        t, body = self.t, self.body
        head = tk.Frame(body, bg=t["bg"])
        head.pack(fill="x", padx=16, pady=(14, 6))
        self.lbl(head, "Rabattcodes", 18, True).pack(side="left")
        self.btn(head, "＋", lambda: self.coupon_dialog(fill), "ok", font=("Segoe UI", 16, "bold"),
                 padx=14, pady=2).pack(side="right")
        tree = ttk.Treeview(body, columns=("code", "pct", "left"), show="headings")
        for c, txt, w in (("code", "Code", 220), ("pct", "Rabatt", 120), ("left", "Noch einlösbar", 160)):
            tree.heading(c, text=txt)
            tree.column(c, width=w, anchor="w")
        tree.pack(fill="both", expand=True, padx=16, pady=6)

        def fill():
            tree.delete(*tree.get_children())
            for c in self.coupons():
                tree.insert("", "end", iid=c["code"], values=(c["code"], f"{c['percent']:g} %", c.get("left", 0)))

        def delete():
            s = tree.selection()
            if s and messagebox.askyesno(APP_NAME, "Rabattcode wirklich löschen?"):
                self.db.save("coupons.json", [c for c in self.coupons() if c["code"] != s[0]])
                fill()
        self.btn(body, "Ausgewählten Code löschen", delete, "bad").pack(anchor="w", padx=16, pady=(0, 14))
        fill()

    def coupon_dialog(self, on_save):
        t = self.t
        d = self.dialog("Rabatt-Gutschein erstellen", 560, 640)
        # Vorlageblatt (Vorschau)
        sheet = tk.Canvas(d, width=470, height=190, bg="#ffffff", highlightthickness=2,
                          highlightbackground=t["accent"])
        sheet.pack(pady=(18, 10))
        sheet.create_text(14, 14, anchor="nw", text=self.store_name, fill="#111", font=("Segoe UI", 15, "bold"))
        pct_txt = sheet.create_text(235, 85, text="-- % Rabatt", fill=t["accent"], font=("Segoe UI", 30, "bold"))
        sheet.create_rectangle(120, 125, 350, 170, fill="#b9bcc2", outline="")
        code_txt = sheet.create_text(235, 148, text="✱ ✱ ✱ ✱ ✱ ✱", fill="#6b6e75", font=("Segoe UI", 16, "bold"))

        f = tk.Frame(d, bg=t["bg"])
        f.pack(fill="x", padx=36)
        self.lbl(f, "Wie viel Prozent Rabatt? (nur die Zahl eingeben)", 11, color=t["muted"]).pack(anchor="w")
        row = tk.Frame(f, bg=t["bg"])
        row.pack(anchor="w", pady=4)
        pv = tk.StringVar()
        self.entry(row, pv, 10).pack(side="left")
        self.lbl(row, "z. B. 25 %", 11, color=t["muted"]).pack(side="left", padx=8)

        def confirm_pct():
            n = parse_num(pv.get())
            if n is None or not 0 < n <= 100:
                return messagebox.showwarning(APP_NAME, "Bitte eine Zahl zwischen 1 und 100 eingeben.", parent=d)
            sheet.itemconfig(pct_txt, text=f"{n:g} % Rabatt")
        self.btn(row, "✔", confirm_pct, "ok", padx=12, pady=3).pack(side="left")

        self.lbl(f, "Code (z. B. sechsstellig)", 11, color=t["muted"]).pack(anchor="w", pady=(14, 0))
        cr = tk.Frame(f, bg=t["bg"])
        cr.pack(anchor="w", pady=4)
        cv = tk.StringVar()
        self.entry(cr, cv, 16).pack(side="left")
        self.btn(cr, "Zufall", lambda: cv.set("".join(random.choice("0123456789") for _ in range(6))),
                 "flat", padx=10, pady=3).pack(side="left", padx=8)
        cv.trace_add("write", lambda *_: sheet.itemconfig(code_txt, text=cv.get() or "✱ ✱ ✱ ✱ ✱ ✱"))
        self.lbl(f, "Anzahl Stück (wie oft einlösbar)", 11, color=t["muted"]).pack(anchor="w", pady=(14, 0))
        qv = tk.StringVar(value="1")
        self.entry(f, qv, 10).pack(anchor="w", pady=4)

        def save():
            n, c = parse_num(pv.get()), cv.get().strip()
            q = int(qv.get()) if qv.get().strip().isdigit() else 0
            if n is None or not 0 < n <= 100 or not c or q < 1:
                return messagebox.showwarning(APP_NAME, "Bitte Prozent, Code und Anzahl korrekt angeben.", parent=d)
            cps = self.coupons()
            for cp in cps:
                if cp["code"] == c:
                    cp.update(percent=n, left=q)
                    break
            else:
                cps.append(dict(code=c, percent=n, left=q, created=dt.datetime.now().isoformat(timespec="seconds")))
            self.db.save("coupons.json", cps)
            d.destroy()
            on_save()
        self.btn(d, "Rabatt-Gutschein einfügen", save, "ok", padx=30).pack(pady=20)

    # ================================================================ GEWINN / VERLUST
    def view_profit(self):
        t, body = self.t, self.body
        head = tk.Frame(body, bg=t["bg"])
        head.pack(fill="x", padx=16, pady=(14, 6))
        self.lbl(head, "Gewinn / Verlust", 18, True).pack(side="left")
        rng = ttk.Combobox(head, values=["Heute", "Gesamt"], state="readonly", width=10)
        rng.current(0)
        rng.pack(side="right")
        cards = tk.Frame(body, bg=t["bg"])
        cards.pack(fill="x", padx=16, pady=6)
        tree = ttk.Treeview(body, columns=("time", "items", "pay", "disc", "rev", "gain"), show="headings", height=9)
        for c, txt, w in (("time", "Zeit", 150), ("items", "Artikel", 90), ("pay", "Zahlart", 90),
                          ("disc", "Rabatt", 90), ("rev", "Umsatz", 110), ("gain", "Gewinn", 110)):
            tree.heading(c, text=txt)
            tree.column(c, width=w, anchor="w")
        tree.pack(fill="both", expand=True, padx=16, pady=6)
        sold = ttk.Treeview(body, columns=("n", "q", "r"), show="headings", height=5)
        for c, txt, w in (("n", "Verkaufte Produkte", 300), ("q", "Menge", 90), ("r", "Umsatz", 120)):
            sold.heading(c, text=txt)
            sold.column(c, width=w, anchor="w")
        sold.pack(fill="x", padx=16, pady=(0, 14))

        def fill(*_):
            for w in cards.winfo_children():
                w.destroy()
            tree.delete(*tree.get_children())
            sold.delete(*sold.get_children())
            today = dt.date.today().isoformat()
            sales = [s for s in self.sales() if rng.get() == "Gesamt" or s["time"].startswith(today)]
            rev = sum(s["total"] for s in sales)
            cost = sum(s["cost"] for s in sales)
            gain = rev - cost
            for txt, val, col in (("Umsatz", rev, t["fg"]), ("Wareneinsatz", cost, t["muted"]),
                                  ("Gewinn" if gain >= 0 else "Verlust", gain, t["ok"] if gain >= 0 else t["bad"])):
                c = tk.Frame(cards, bg=t["panel"])
                c.pack(side="left", padx=(0, 10), ipadx=14, ipady=6)
                self.lbl(c, txt, 10, color=t["muted"], bg=t["panel"]).pack(anchor="w")
                self.lbl(c, money(val), 18, True, col, bg=t["panel"]).pack(anchor="w")
            agg = {}
            for s in reversed(sales):
                tree.insert("", "end", values=(s["time"].replace("T", " "), sum(i["qty"] for i in s["items"]),
                                               s["method"], f"{s['percent']:g} %" if s["percent"] else "-",
                                               money(s["total"]), money(s["total"] - s["cost"])))
                for i in s["items"]:
                    a = agg.setdefault(i["name"], [0, 0.0])
                    a[0] += i["qty"]
                    a[1] += i["qty"] * i["price"]
            for n, (q, r) in sorted(agg.items(), key=lambda x: -x[1][1]):
                sold.insert("", "end", values=(n, q, money(r)))
        rng.bind("<<ComboboxSelected>>", fill)
        fill()

    # ================================================================ EINSTELLUNGEN
    def view_settings(self):
        t, c = self.t, self.db.cfg
        sf = ScrollFrame(self.body, t["bg"])
        sf.pack(fill="both", expand=True, padx=30, pady=10)
        b = sf.inner
        profile = self.db.load("profile.json", {})

        def section(txt):
            self.lbl(b, txt, 14, True, t["accent"]).pack(anchor="w", pady=(22, 6))

        # Ordner (ganz oben)
        section("Speicherordner")
        dirvar = tk.StringVar(value=c["data_dir"])
        self.lbl(b, "Hier werden alle Daten gespeichert (Produkte, Gutscheincodes, Verkäufe ...):", 10,
                 color=t["muted"]).pack(anchor="w")
        r = tk.Frame(b, bg=t["bg"])
        r.pack(anchor="w", fill="x", pady=4)
        self.entry(r, dirvar, 60, state="readonly").pack(side="left")

        def pick_dir():
            d = filedialog.askdirectory(initialdir=c["data_dir"])
            if d:
                self.db.move_data(d)
                dirvar.set(d)
                messagebox.showinfo(APP_NAME, "Daten wurden in den neuen Ordner kopiert.")
        self.btn(r, "Ändern", pick_dir, "flat").pack(side="left", padx=8)

        # Profil
        section("Deine Infos")
        keys = [("Name", "first"), ("Nachname", "last"), ("Telefonnummer", "phone"), ("E-Mail", "email"),
                ("Name des Stores", "store"), ("Adresse", "address")]
        pv = {k: tk.StringVar(value=profile.get(k, "")) for _, k in keys}
        g = tk.Frame(b, bg=t["bg"])
        g.pack(anchor="w")
        for i, (txt, k) in enumerate(keys):
            self.lbl(g, txt, 11, color=t["muted"]).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 16))
            self.entry(g, pv[k], 36).grid(row=i, column=1, pady=4)

        def save_profile():
            self.db.save("profile.json", {k: pv[k].get().strip() for k in pv})
            self.show_main("settings")
        self.btn(b, "Infos speichern (überschreibt)", save_profile, "accent").pack(anchor="w", pady=8)

        # Logos
        section("Logos")

        def logo_row(txt, key):
            rr = tk.Frame(b, bg=t["bg"])
            rr.pack(anchor="w", pady=4)
            self.lbl(rr, txt, 11, color=t["muted"], width=26, anchor="w").pack(side="left")
            name = self.lbl(rr, os.path.basename(c[key]) or "kein Logo", 11)
            name.pack(side="left", padx=8)

            def pick():
                fn = filedialog.askopenfilename(filetypes=[("PNG / Bilder", "*.png *.gif *.jpg *.jpeg")])
                if fn:
                    c[key] = self.db.import_image(fn) if False else self.copy_logo(fn)
                    self.db.save_cfg()
                    self.show_main("settings")

            def reset():
                c[key] = ""
                self.db.save_cfg()
                self.show_main("settings")
            self.btn(rr, "PNG auswählen", pick, "flat", padx=10, pady=4).pack(side="left", padx=4)
            self.btn(rr, "Entfernen", reset, "flat", padx=10, pady=4).pack(side="left")
        logo_row("App-Logo (Startbildschirm)", "app_logo")
        logo_row("Boot-Logo (Ladefenster)", "boot_logo")

        # Geräte
        section("Geräte")
        mode = tk.StringVar(value=c["scanner_mode"])
        mf = tk.Frame(b, bg=t["bg"])
        mf.pack(anchor="w")
        combo = ttk.Combobox(b, state="readonly", width=62)

        def refresh_dev(*_):
            combo["values"] = detect_serial_ports() if mode.get() == "Barcode-Scanner" else detect_cameras()
            cur = c["scanner_device"] if mode.get() == "Barcode-Scanner" else c["camera_device"]
            combo.set(cur if cur in combo["values"] else combo["values"][0])
        for txt in ("Barcode-Scanner", "Kamera"):
            tk.Radiobutton(mf, text=txt, variable=mode, value=txt, command=refresh_dev, bg=t["bg"], fg=t["fg"],
                           selectcolor=t["entry"], activebackground=t["bg"], activeforeground=t["fg"],
                           font=("Segoe UI", 11)).pack(side="left", padx=(0, 18))
        combo.pack(anchor="w", pady=6)
        refresh_dev()
        self.lbl(b, "Kartenzahlung (Gerät / Anbieter, z. B. SumUp):", 11, color=t["muted"]).pack(anchor="w", pady=(10, 2))
        card = ttk.Combobox(b, values=["", "SumUp", "Zettle", "Stripe Terminal", "Anderes Gerät"], width=30)
        card.set(c["card_device"])
        card.pack(anchor="w")

        # Design / PIN
        section("Design & Sicherheit")
        self.lbl(b, "Design:", 11, color=t["muted"]).pack(anchor="w")
        theme = ttk.Combobox(b, values=list(THEMES), state="readonly", width=20)
        theme.set(c["theme"])
        theme.pack(anchor="w", pady=(2, 10))
        self.lbl(b, "PIN beim Start (leer = keine PIN):", 11, color=t["muted"]).pack(anchor="w")
        pinv = tk.StringVar(value=c["pin"])
        self.entry(b, pinv, 14, show="•").pack(anchor="w", pady=2)

        def save_all():
            pin = pinv.get().strip()
            if pin and not pin.isdigit():
                return messagebox.showwarning(APP_NAME, "Die PIN darf nur aus Zahlen bestehen.")
            c.update(scanner_mode=mode.get(), card_device=card.get(), theme=theme.get(), pin=pin)
            c["scanner_device" if mode.get() == "Barcode-Scanner" else "camera_device"] = combo.get()
            self.db.save_cfg()
            self.show_main("settings")
        self.btn(b, "Einstellungen speichern", save_all, "ok", pady=10).pack(anchor="w", pady=(18, 4))

        # Abmelden (ganz unten)
        section("Konto")
        self.btn(b, "Abmelden", self.logout, "bad").pack(anchor="w", pady=(0, 60))

    def copy_logo(self, src):
        os.makedirs(self.db.cfg["data_dir"], exist_ok=True)
        dst = os.path.join(self.db.cfg["data_dir"], "logo_" + uuid.uuid4().hex[:6] + os.path.splitext(src)[1])
        shutil.copy(src, dst)
        return dst

    def logout(self):
        if not messagebox.askyesno("Abmelden", "Wollen Sie sich wirklich abmelden?\n\n"
                                               "Ihre Daten können Sie jederzeit in Ihrem festgelegten Ordner finden."):
            return
        folder = self.db.cfg["data_dir"]
        self.db.cfg["setup_done"] = False
        self.db.save_cfg()
        messagebox.showinfo("Abgemeldet", "Ihre Daten können Sie jederzeit in Ihrem festgelegten Ordner finden:\n\n"
                            + folder)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
