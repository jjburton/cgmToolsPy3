"""
mrsAnimClip — MRS context wrapper around cgmAnimClip.

PoseManager context chrome (control / part / puppet / scene / list + core /
children / siblings / mirror) pinned above the inherited AnimClip Dat UI.
Clip schema, curve IO, Capture / Current Clip / Apply stay in animClip_dat.
Do not import Animate.py into animClip_dat.
"""
__MAYALOCAL = 'MRSANIMCLIP'

import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

from cgm.core import cgm_General as cgmGEN
from cgm.core.classes import GuiFactory as CGMUI
import cgm.core.lib.animClip_dat as ANIMCLIPDAT
import cgm.core.mrs.lib.animate_utils as MRSANIMUTILS

log_msg = cgmGEN.logString_msg
__version__ = cgmGEN.__RELEASESTRING


class ui(ANIMCLIPDAT.ui):
    USE_Template = 'cgmUITemplate'
    _toolname = 'mrsAnimClip'
    TOOLNAME = 'ui_mrsAnimClip'
    WINDOW_NAME = '{}UI'.format(TOOLNAME)
    WINDOW_TITLE = 'mrsAnimClip | {0}'.format(__version__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = False
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True
    DEFAULT_SIZE = 560, 700

    _datClass = ANIMCLIPDAT.AnimClip

    def reload(self):
        cgmGEN._reloadMod(MRSANIMUTILS)
        cgmGEN._reloadMod(ANIMCLIPDAT)
        ANIMCLIPDAT.reload_dependencies()
        import cgm.core.mrs.mrsAnimClip as MRSANIMCLIP
        cgmGEN._reloadMod(MRSANIMCLIP)
        CGMUI.cgmGUI.reload(self)

    def insert_init(self, *args, **kws):
        ANIMCLIPDAT.ui.insert_init(self, *args, **kws)
        MRSANIMUTILS.uiSetup_context(self, self.__class__.TOOLNAME)
        self.mDat = MRSANIMUTILS.get_sharedDatObject()

    def uiBuild_pinned_chrome(self, parent):
        return MRSANIMUTILS.uiColumn_context(self, parent, header=True)

    def _clip_source_label(self):
        return 'From MRS context (select a seed; scene needs none).'

    def _clip_empty_capture_msg(self):
        return 'No MRS context controls to capture'

    def _clip_empty_apply_msg(self):
        return 'No MRS context dests to paste'

    def _clip_capture_nodes(self):
        return self._context_nodes()

    def _clip_apply_dests(self):
        return self._context_nodes()

    def _context_nodes(self):
        """Transform longs from PoseManager context_get. Empty list if none."""
        _str_func = '_context_nodes'
        if not getattr(self, 'mDat', None):
            self.mDat = MRSANIMUTILS.get_sharedDatObject()
        try:
            _dat = MRSANIMUTILS.get_contextDict(self.__class__.TOOLNAME)
            raw = self.mDat.context_get(**_dat)
        except Exception as err:
            log.warning(log_msg(_str_func, err))
            return []
        if not raw:
            return []
        nodes = ANIMCLIPDAT._normalize_nodes(raw)
        log.debug(log_msg(_str_func, '{} controls'.format(len(nodes))))
        return nodes
