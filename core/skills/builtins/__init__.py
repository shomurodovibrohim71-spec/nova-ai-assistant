from .file_io import ReadFileSkill, WriteFileSkill
from .presentation_skill import PresentationSkill
from .post_design_skill import PostDesignSkill
from .google_drive import GoogleDriveSkill
from .canva_skill import CanvaSkill
from .files import (
    CopySkill,
    DeleteSkill,
    FindFilesSkill,
    ListDirSkill,
    MakeDirSkill,
    MoveSkill,
    ZipSkill,
)
from .excel_query import ExcelQuerySkill
from .open_app import CloseAppSkill, InstallAppSkill, OpenAppSkill
from .ping import PingSkill
from .screenshot import ScreenshotSkill
from .system_info import SystemInfoSkill
from .telegram_skill import TelegramSendFileSkill, TelegramSendMessageSkill
from .web import WebFetchSkill, WebSearchSkill


def load_builtin_skills(registry, memory=None) -> None:
    for skill_cls in (
        PingSkill,
        OpenAppSkill,
        CloseAppSkill,
        InstallAppSkill,
        SystemInfoSkill,
        ScreenshotSkill,
        ExcelQuerySkill,
        # files
        ListDirSkill,
        FindFilesSkill,
        MakeDirSkill,
        MoveSkill,
        CopySkill,
        DeleteSkill,
        ZipSkill,
        ReadFileSkill,
        WriteFileSkill,
        # web
        WebSearchSkill,
        WebFetchSkill,
        # telegram
        TelegramSendMessageSkill,
        TelegramSendFileSkill,
        GoogleDriveSkill,
        CanvaSkill,
        PresentationSkill,
        PostDesignSkill,
    ):
        registry.register(skill_cls())

    if memory is not None:
        from .memory_skill import ForgetSkill, RecallSkill, RememberSkill

        registry.register(RememberSkill(memory))
        registry.register(RecallSkill(memory))
        registry.register(ForgetSkill(memory))


__all__ = ["load_builtin_skills"]
