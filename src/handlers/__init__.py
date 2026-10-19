"""snowluma_full 的事件处理器：能力目录注入 + payload 层折叠。"""

from .catalog_handler import CatalogHandler
from .fold_handler import FoldHandler

__all__ = ["CatalogHandler", "FoldHandler"]
