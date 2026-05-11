from __future__ import annotations

try:
    import tkinter as tk
    from tkinter import ttk
except Exception as exc:  # pragma: no cover - depends on local Python build
    tk = None
    ttk = None
    TK_IMPORT_ERROR = exc
else:
    TK_IMPORT_ERROR = None

from .diagnostics import charging_diagnostic, summary_for, trust_flags
from .formatters import filter_identities, filter_sources
from .models import Endpoint
from .sysfs import snapshot

STATUS_COLORS = {
    "empty": "#667085",
    "charging": "#b54708",
    "dataDevice": "#175cd3",
    "thunderboltCable": "#7a2e98",
    "displayCable": "#027a48",
    "unknown": "#b54708",
}


class WhatCableTkApp:  # pragma: no cover - exercised manually
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("WhatCable Py")
        self.root.geometry("640x760")
        self.root.minsize(440, 420)
        self.show_raw = tk.BooleanVar(value=False)
        self.hide_empty = tk.BooleanVar(value=False)
        self._build_shell()
        self.refresh()
        self.root.after(2000, self._tick)

    def run(self) -> int:
        self.root.mainloop()
        return 0

    def _build_shell(self) -> None:
        self.root.configure(bg="#f5f6f8")
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        self.style.configure("Toolbar.TFrame", background="#f5f6f8")
        self.style.configure("Title.TLabel", background="#f5f6f8", foreground="#101828", font=("Sans", 18, "bold"))
        self.style.configure("Subtitle.TLabel", background="#f5f6f8", foreground="#667085", font=("Sans", 10))
        self.style.configure("Card.TFrame", background="#ffffff", relief="solid", borderwidth=1)
        self.style.configure("Port.TLabel", background="#ffffff", foreground="#667085", font=("Sans", 9, "bold"))
        self.style.configure("Headline.TLabel", background="#ffffff", foreground="#101828", font=("Sans", 15, "bold"))
        self.style.configure("Body.TLabel", background="#ffffff", foreground="#344054", font=("Sans", 10))
        self.style.configure("Dim.TLabel", background="#ffffff", foreground="#667085", font=("Sans", 10))
        self.style.configure("Warn.TLabel", background="#ffffff", foreground="#b54708", font=("Sans", 10, "bold"))
        self.style.configure("Raw.TLabel", background="#ffffff", foreground="#475467", font=("Monospace", 9))

        header = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(18, 16, 18, 8))
        header.pack(fill="x")
        ttk.Label(header, text="WhatCable Py", style="Title.TLabel").pack(anchor="w")
        ttk.Label(header, text="What can this USB-C cable actually do?", style="Subtitle.TLabel").pack(anchor="w", pady=(2, 0))

        toolbar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(18, 0, 18, 10))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Checkbutton(toolbar, text="Raw", variable=self.show_raw, command=self.refresh).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(toolbar, text="Hide empty", variable=self.hide_empty, command=self.refresh).pack(side="left", padx=(10, 0))

        self.canvas = tk.Canvas(self.root, bg="#f5f6f8", highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.content = ttk.Frame(self.canvas, style="Toolbar.TFrame")
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_content_configure(self, _event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _tick(self) -> None:
        self.refresh()
        self.root.after(2000, self._tick)

    def refresh(self) -> None:
        for child in self.content.winfo_children():
            child.destroy()
        snap = snapshot()
        visible = 0
        for port in snap.ports:
            identities = filter_identities(port, snap.identities)
            sources = filter_sources(port, snap.power_sources)
            summary = summary_for(port, sources, identities)
            if self.hide_empty.get() and summary.status == "empty":
                continue
            visible += 1
            self._add_card(port, summary, sources, identities)
        if visible == 0:
            empty = ttk.Label(
                self.content,
                text="No USB-C / removable USB ports were found on this system.",
                style="Subtitle.TLabel",
                padding=(18, 22, 18, 0),
                wraplength=520,
            )
            empty.pack(fill="x")

    def _add_card(self, port, summary, sources, identities) -> None:
        card = ttk.Frame(self.content, style="Card.TFrame", padding=(14, 12, 14, 12))
        card.pack(fill="x", padx=18, pady=8)
        ttk.Label(card, text=f"{port.label} ({port.port_type_description or 'USB'})", style="Port.TLabel").pack(anchor="w")
        headline = ttk.Label(card, text=summary.headline, style="Headline.TLabel", wraplength=560)
        headline.pack(anchor="w", pady=(4, 0))
        headline.configure(foreground=STATUS_COLORS.get(summary.status, "#101828"))
        ttk.Label(card, text=summary.subtitle, style="Dim.TLabel", wraplength=560).pack(anchor="w", pady=(2, 8))

        for bullet in summary.bullets:
            ttk.Label(card, text=f"• {bullet}", style="Body.TLabel", wraplength=560).pack(anchor="w", pady=1)

        diag = charging_diagnostic(port, sources, identities)
        if diag:
            style = "Warn.TLabel" if diag.is_warning else "Body.TLabel"
            ttk.Label(card, text=f"Charging: {diag.summary}\n{diag.detail}", style=style, wraplength=560).pack(anchor="w", pady=(8, 0))

        cable = next((i for i in identities if i.endpoint in {Endpoint.SOP_PRIME, Endpoint.SOP_DOUBLE_PRIME}), None)
        if cable:
            flags = trust_flags(cable)
            if flags:
                ttk.Label(card, text="Cable trust signals:\n" + "\n".join(f"! {flag}" for flag in flags), style="Warn.TLabel", wraplength=560).pack(anchor="w", pady=(8, 0))

        if self.show_raw.get():
            raw = "\n".join(f"{key} = {value}" for key, value in sorted(port.raw_properties.items()))
            ttk.Label(card, text="Raw sysfs properties:", style="Port.TLabel").pack(anchor="w", pady=(10, 2))
            ttk.Label(card, text=raw or "(none)", style="Raw.TLabel", wraplength=560, justify="left").pack(anchor="w")


def main() -> int:
    if tk is None:
        print("Tkinter is not available for this Python interpreter.")
        print("On Ubuntu system Python, install it with: sudo apt install python3-tk")
        print("If you use pyenv, install tk-dev and rebuild/reinstall that Python version.")
        print(f"Import error: {TK_IMPORT_ERROR}")
        return 1
    try:
        return WhatCableTkApp().run()
    except tk.TclError as exc:
        print("Could not open a desktop window. Are you running inside a graphical Ubuntu session?")
        print(f"Tk error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
