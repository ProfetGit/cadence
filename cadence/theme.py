from PyQt6.QtGui import QColor

from .settings import Settings


def build_css(s: Settings, accent: QColor) -> str:
    a = accent.name()
    css = [
        ":root{--cadence-accent:%s;}" % a,
        "::-webkit-scrollbar{width:12px;height:12px;background:transparent;}",
        "::-webkit-scrollbar-track{background:transparent;}",
        "::-webkit-scrollbar-thumb{background:rgba(255,255,255,.16);border-radius:8px;"
        "border:3px solid transparent;background-clip:content-box;}",
        "::-webkit-scrollbar-thumb:hover{background:rgba(255,255,255,.32);background-clip:content-box;"
        "border:3px solid transparent;}",
        "::-webkit-scrollbar-corner{background:transparent;}",
        "html{scrollbar-color:auto;}",
        "ytmusic-app{-webkit-font-smoothing:antialiased;}",
        "ytmusic-nav-bar{border-bottom:none!important;}",
        "::selection{background:%s;color:#000;}" % a,
    ]
    if s["hide_web_logo"]:
        css.append("ytmusic-nav-bar ytmusic-logo{display:none!important;}")
    if s["native_bar"]:
        css.append("ytmusic-player-bar,ytmusic-miniplayer{display:none!important;}")
        css.append("ytmusic-app-layout{--ytmusic-player-bar-height:0px!important;}")
    return "\n".join(css)
