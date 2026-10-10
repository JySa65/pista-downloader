import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os, sys, re, io, webbrowser
from urllib.parse import urlparse, parse_qs

# --- dependencias principales ---
try:
    import yt_dlp
except ImportError:
    raise SystemExit("Instala yt-dlp: pip install yt-dlp")

# --- opcionales para miniaturas ---
HAS_IMG = False
try:
    import requests
    from PIL import Image, ImageTk
    HAS_IMG = True
except Exception:
    HAS_IMG = False

APP_TITLE = "YouTube → MP3 (Lote + Info) – yt-dlp + Tkinter"
DEFAULT_QUALITY = "192"  # kbps

def normalize_youtube_url(url: str) -> str:
    """Si no seguimos playlists (noplaylist=True), conviene normalizar a v=<id>."""
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        vid = qs.get("v", [None])[0]
        return f"https://www.youtube.com/watch?v={vid}" if vid else url.strip()
    except Exception:
        return url.strip()

def hhmmss(seconds: int | float | None) -> str:
    if not seconds:
        return "?"
    seconds = int(seconds)
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"

class UIBase:
    def ui(self, fn, *a, **kw):
        self.after(0, lambda: fn(*a, **kw))
    def set_status(self, t): self.status_var.set(t)
    def set_pvideo(self, v): self.pvideo_var.set(v)
    def set_pbatch(self, v): self.pbatch_var.set(v)
    def set_file(self, t): self.file_var.set(t)
    def log(self, t): self.txt.insert("end", t); self.txt.see("end")
    def alert(self, title, msg): self.ui(messagebox.showerror, title, msg)

class App(tk.Tk, UIBase):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x720")
        self.minsize(920, 640)

        # Estado
        self.outdir = tk.StringVar(value=os.path.expanduser("~/Music"))
        self.kbps = tk.StringVar(value=DEFAULT_QUALITY)
        self.follow_playlists = tk.BooleanVar(value=False)     # controla noplaylist
        self.show_info = tk.BooleanVar(value=True)             # bool para metadatos
        self.status_var = tk.StringVar(value="Listo.")
        self.pvideo_var = tk.DoubleVar(value=0.0)              # progreso item
        self.pbatch_var = tk.DoubleVar(value=0.0)              # progreso lote
        self.file_var = tk.StringVar(value="")
        self.is_downloading = False
        self.stop_flag = False

        self._build_ui()

    # ---------------- UI ----------------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        root = ttk.Frame(self); root.pack(fill="both", expand=True)

        # fila 0: carpeta + calidad + flags
        r = 0
        ttk.Label(root, text="Carpeta:").grid(row=r, column=0, sticky="w", **pad)
        ttk.Entry(root, textvariable=self.outdir, width=50).grid(row=r, column=1, sticky="we", **pad)
        ttk.Button(root, text="Elegir…", command=self.choose_dir).grid(row=r, column=2, sticky="we", **pad)

        r += 1
        opt = ttk.Frame(root); opt.grid(row=r, column=0, columnspan=3, sticky="we", **pad)
        ttk.Label(opt, text="Calidad MP3:").pack(side="left")
        ttk.Combobox(opt, textvariable=self.kbps, values=["128","160","192","256","320"],
                     state="readonly", width=6).pack(side="left", padx=(6,16))
        ttk.Checkbutton(opt, text="Seguir playlists/Mix (noplaylist=False)", variable=self.follow_playlists).pack(side="left")
        ttk.Checkbutton(opt, text="Mostrar info (metadatos)", variable=self.show_info).pack(side="left", padx=(16,0))

        # fila 2: URLs
        r += 1
        ttk.Label(root, text="URLs (una por línea):").grid(row=r, column=0, columnspan=3, sticky="w", **pad)
        r += 1
        self.url_text = tk.Text(root, height=5)
        self.url_text.grid(row=r, column=0, columnspan=3, sticky="we", padx=10, pady=(0,6))

        # fila 4: botones superior
        r += 1
        btns = ttk.Frame(root); btns.grid(row=r, column=0, columnspan=3, sticky="we", **pad)
        ttk.Button(btns, text="Pegar del portapapeles", command=self.paste_clipboard).pack(side="left", padx=5)
        ttk.Button(btns, text="Limpiar URLs", command=self.clear_urls).pack(side="left", padx=5)
        ttk.Button(btns, text="Cargar info", command=self.load_info_thread).pack(side="left", padx=5)
        ttk.Button(btns, text="Descargar MP3 (lote)", command=self.start_batch_thread).pack(side="left", padx=5)
        self.btn_stop = ttk.Button(btns, text="Detener", command=self.request_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=5)

        # fila 5: split: tabla info + preview panel
        r += 1
        split = ttk.Frame(root); split.grid(row=r, column=0, columnspan=3, sticky="nsew", padx=10, pady=6)
        root.rowconfigure(r, weight=1)

        # Tabla info
        left = ttk.Frame(split); left.pack(side="left", fill="both", expand=True)
        cols = ("#","title","channel","duration","url")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=10)
        for c, w, t in [("#",50,"#"),("title",320,"Título"),("channel",180,"Canal"),
                        ("duration",90,"Duración"),("url",300,"URL")]:
            self.tree.heading(c, text=t); self.tree.column(c, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        ttk.Scrollbar(left, command=self.tree.yview).pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=lambda *a: None)
        self.tree.bind("<Double-1>", self.on_tree_double)

        # Panel miniatura
        right = ttk.Frame(split, width=380); right.pack(side="left", fill="y")
        ttk.Label(right, text="Miniatura").pack(anchor="w")
        self.thumb_label = ttk.Label(right)
        self.thumb_label.pack(pady=6)
        ttk.Button(right, text="Abrir en navegador", command=self.open_selected).pack(anchor="w", pady=6)

        # fila 6: progresos y archivo
        r += 1
        ttk.Label(root, text="Progreso (video):").grid(row=r, column=0, sticky="w", **pad)
        ttk.Progressbar(root, variable=self.pvideo_var, maximum=100).grid(row=r, column=1, sticky="we", **pad)
        ttk.Label(root, textvariable=self.file_var).grid(row=r, column=2, sticky="we", **pad)

        r += 1
        ttk.Label(root, text="Progreso (lote):").grid(row=r, column=0, sticky="w", **pad)
        ttk.Progressbar(root, variable=self.pbatch_var, maximum=100).grid(row=r, column=1, columnspan=2, sticky="we", **pad)

        # fila 8: log
        r += 1
        ttk.Label(root, text="Log:").grid(row=r, column=0, columnspan=3, sticky="w", **pad)
        r += 1
        self.txt = tk.Text(root, height=8, wrap="word")
        self.txt.grid(row=r, column=0, columnspan=3, sticky="nsew", padx=10, pady=(0,10))
        ttk.Scrollbar(root, command=self.txt.yview).grid(row=r, column=3, sticky="ns", pady=(0,10))
        root.rowconfigure(r, weight=1)

        # status bar
        ttk.Label(self, textvariable=self.status_var, anchor="w").pack(side="bottom", fill="x", padx=10, pady=6)

    # ------------- helpers UI -------------
    def choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.outdir.get() or os.path.expanduser("~"))
        if d: self.outdir.set(d)

    def paste_clipboard(self):
        try: text = self.clipboard_get()
        except tk.TclError: text = ""
        if text: self.url_text.insert("end", text.strip() + ("\n" if not text.endswith("\n") else ""))

    def clear_urls(self):
        self.url_text.delete("1.0", "end")
        for i in self.tree.get_children(): self.tree.delete(i)
        self.thumb_label.configure(image=""); self.thumb_label.image = None

    def _collect_urls(self):
        lines = [ln.strip() for ln in self.url_text.get("1.0","end").splitlines() if ln.strip()]
        urls = [u for u in lines if u.lower().startswith(("http://","https://"))]
        seen, ordered = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u); ordered.append(u)
        return ordered

    # ------------- INFO (metadatos) -------------
    def load_info_thread(self):
        urls = self._collect_urls()
        if not self.show_info.get():
            self.alert("Info desactivada", "Activa «Mostrar info (metadatos)» para cargar información.")
            return
        if not urls:
            self.alert("Faltan URLs", "Pega al menos una URL (http/https).")
            return

        # Limpia tabla y miniatura antes de empezar
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.thumb_label.configure(image=""); self.thumb_label.image = None

        self.set_status("Extrayendo metadatos…")
        self.log(f"ℹ️ Cargando info de {len(urls)} URL(s)\n")
        t = threading.Thread(target=self._load_info_worker, args=(urls,), daemon=True)
        t.start()

    def _load_info_worker(self, urls):
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            # Evita expandir playlists al consultar info (más rápido y predecible)
            "noplaylist": True,
            "extract_flat": "discard_in_playlist",  # devuelve datos básicos sin expandir
        }

        total = len(urls)
        for idx, raw in enumerate(urls, start=1):
            url = raw.strip()
            self.ui(self.set_status, f"Extrayendo metadatos… [{idx}/{total}]")
            self.ui(self.log, f"→ {url}\n")

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                # Si es una playlist “plana”, intenta tomar primer elemento
                if isinstance(info, dict) and info.get("_type") == "playlist":
                    entries = info.get("entries") or []
                    if entries:
                        # los entries de extract_flat traen claves como 'title', 'uploader', 'duration'
                        info = entries[0]

                title = info.get("title") or "(sin título)"
                channel = info.get("uploader") or info.get("uploader_id") or "?"
                duration = hhmmss(info.get("duration"))

                # Inserta fila en tabla
                self.ui(self.tree.insert, "", "end", values=(idx, title, channel, duration, raw))

                # Miniatura (si está disponible y tienes Pillow+requests)
                if HAS_IMG:
                    thumb = (info.get("thumbnail") or
                            (info.get("thumbnails") or [{}])[-1].get("url") if isinstance(info.get("thumbnails"), list) else None)
                    if thumb:
                        # Llama a la función existente que setea la miniatura
                        self.ui(self._try_set_thumbnail, thumb)

            except Exception as e:
                self.ui(self.log, f"❌ Error metadatos [{idx}/{total}] {url}: {e}\n")

        self.ui(self.set_status, "Listo.")

    def _try_set_thumbnail(self, url):
        if not HAS_IMG: return
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content))
            img.thumbnail((360, 360))
            tkimg = ImageTk.PhotoImage(img)
            self.thumb_label.configure(image=tkimg)
            self.thumb_label.image = tkimg
        except Exception:
            pass

    def on_tree_double(self, _evt):
        self.open_selected()

    def open_selected(self):
        sel = self.tree.selection()
        if not sel:
            self.alert("Sin selección", "Haz doble clic en una fila o selecciónala primero.")
            return
        webbrowser.open(self.tree.item(sel[0])["values"][-1])

    # ------------- DESCARGA MP3 (lote) -------------
    def request_stop(self):
        self.stop_flag = True

    def start_batch_thread(self):
        if self.is_downloading:
            return
        urls = self._collect_urls()
        if not urls:
            self.alert("Faltan URLs", "Pega al menos una URL válida.")
            return
        if not os.path.isdir(self.outdir.get()):
            self.alert("Carpeta inválida", "Selecciona una carpeta de salida válida.")
            return
        self.is_downloading = True
        self.stop_flag = False
        self.btn_stop.config(state="normal")
        self.set_pvideo(0); self.set_pbatch(0)
        self.set_status("Preparando lote…")
        self.log(f"▶ Lote con {len(urls)} URL(s)\n")
        threading.Thread(target=self._batch_worker, args=(urls,), daemon=True).start()

    def _batch_worker(self, urls):
        total = len(urls)
        for i, raw in enumerate(urls, start=1):
            if self.stop_flag:
                self.ui(self.log, "⏹ Detenido por el usuario.\n")
                break
            follow = self.follow_playlists.get()
            url = raw if follow else normalize_youtube_url(raw)
            self.ui(self.set_status, f"[{i}/{total}] Descargando…")
            self.ui(self.set_pvideo, 0.0)
            self.ui(self.log, f"\n[{i}/{total}] → {url}\n")
            ok = self._download_one(url, follow)
            self.ui(self.set_pbatch, i/total*100.0)
            if not ok:
                self.ui(self.log, f"❌ Falló [{i}/{total}]\n")
        self.is_downloading = False
        self.ui(self.set_status, "Lote finalizado." + (" (detenido)" if self.stop_flag else ""))
        self.ui(self.btn_stop.config, {"state": "disabled"})

    def _download_one(self, url, follow_playlists: bool) -> bool:
        quality = self.kbps.get() or DEFAULT_QUALITY
        outtmpl = os.path.join(self.outdir.get(), "%(title)s.%(ext)s")

        def hook(d):
            st = d.get("status")
            if st == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                dl = d.get("downloaded_bytes") or 0
                pct = (dl/total*100) if total else 0
                title = (d.get("info_dict") or {}).get("title") or ""
                self.ui(self.set_pvideo, pct)
                self.ui(self.set_file, self._safe(title))
                self.ui(self.set_status, f"Descargando… {pct:0.1f}%")
            elif st == "finished":
                self.ui(self.set_status, "Convirtiendo a MP3…")
                self.ui(self.set_pvideo, 95)

        ydl_opts = {
            "noplaylist": (not follow_playlists),
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            }],
            "quiet": True, "no_warnings": True,
            "progress_hooks": [hook],
            "retries": 5, "fragment_retries": 5,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                # playlist vs video
                if isinstance(info, dict) and info.get("_type") == "playlist":
                    self.ui(self.log, f"ℹ️ Playlist procesada: {info.get('title','(sin título)')}\n")
                else:
                    title = info.get("title","audio")
                    fname = self._safe(title) + ".mp3"
                    final_path = os.path.join(self.outdir.get(), fname)
                    self.ui(self.set_file, fname)
                    self.ui(self.log, f"✅ Guardado: {final_path}\n")
                self.ui(self.set_pvideo, 100); self.ui(self.set_status, "¡Listo!")
            return True
        except yt_dlp.utils.DownloadError as e:
            self.ui(self.set_status, "Error de descarga.")
            self.ui(self.log, f"❌ DownloadError: {e}\n")
            self.ui(messagebox.showerror, "Error de descarga", str(e))
        except Exception as e:
            self.ui(self.set_status, "Error.")
            self.ui(self.log, f"❌ Error: {e}\n")
            self.ui(messagebox.showerror, "Error", str(e))
        return False

    # -------- util --------
    def _safe(self, name: str) -> str:
        name = re.sub(r'[\\/*?:"<>|]+', "_", name)
        return re.sub(r"\s+", " ", name).strip()

def main():
    # macOS foco
    if sys.platform == "darwin":
        try:
            from ctypes import cdll
            cdll.LoadLibrary('/System/Library/Frameworks/Carbon.framework/Carbon')
        except Exception: pass
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()
