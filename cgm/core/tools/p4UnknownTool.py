"""
------------------------------------------
p4UnknownTool : cgm.core.tools
Find local project files not on Perforce depot — Scene → Tools → Perforce.
------------------------------------------
"""
import logging
import os
import stat

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

import maya.cmds as mc

import cgm.core.classes.GuiFactory as cgmUI
import cgm.core.cgm_Meta as cgmMeta
import cgm.core.cgm_General as cgmGEN
import cgm.core.cgmPy.path_Utils as PATHS
import cgm.core.lib.math_utils as MATH
import cgm.core.lib.perforce as P4UTIL
import cgm.images.icons as cgmIcons

from cgm.core.tools.p4Tool import (
    uiFunc_p4_progress_begin,
    uiFunc_p4_progress_end,
    uiFunc_p4_progress_update,
    uiFunc_prompt_changelist_target,
    uiFunc_set_status_panel,
    _ROW_BGC_EVEN,
    _ROW_BGC_ODD,
    _icon_btn_kw,
)

mUI = cgmUI.mUI
_path_imageFolder = PATHS.Path(cgmIcons.__file__).up().asFriendly()

__version__ = cgmGEN.__RELEASESTRING
__toolname__ = 'cgmP4FindUnknowns'
_padding = 5
_edge_padding = 5
_UNKNOWN_EXT_FILTER_BGC = [.66, .70, .78]
_UNKNOWN_EXT_ALL = '__all__'
_UNKNOWN_EXT_NONE = '(none)'
_UNKNOWN_EXT_GRID_COLS = 5
_UNKNOWN_EXT_CELL_WH = (72, 18)
_UNKNOWN_CTRL_ROW_H = 24
_UNKNOWN_SEARCH_ROW_H = 22
_PROJECT_SCOPE = 'project'


def reload_tool():
    import cgm.core.tools.p4Tool as P4TOOL
    cgmGEN._reloadMod(P4TOOL)
    P4TOOL.reload_dependencies()
    cgmGEN._reloadMod(__import__(__name__))


def _ui_layout_current(self):
    """RETAIN windows can outlive layout changes; require current widgets."""
    return (
        hasattr(self, 'uiLabel_status')
        and hasattr(self, 'uiLabel_connection')
        and hasattr(self, 'uiColumn_unknown')
        and hasattr(self, 'uiScroll_unknown_files')
        and hasattr(self, 'uiRow_cgm_footer')
    )


class ui(cgmUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    WINDOW_NAME = '{0}_ui'.format(__toolname__)
    WINDOW_TITLE = '{1} - {0}'.format(__version__, __toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = False
    DEFAULT_SIZE = 400, 520
    TOOLNAME = '{0}.ui'.format(__toolname__)

    def insert_init(self, *args, **kws):
        self._l_unknown_entries = []
        self._l_unknown_entries_all = []
        self._d_unknown_ui = {}
        self.var_unknown_ext_enabled = cgmMeta.cgmOptionVar(
            'cgmVar_p4_unknown_ext_filter', varType='string', defaultValue=_UNKNOWN_EXT_ALL)
        self._d_unknown_ext_ui = {}
        self._l_unknown_ext_keys = []
        self._d_unknown_checked = {}
        self._scan_root = None
        self._scan_dir_mask = None
        self._p4_status_dat = None

    def _build_collapse_frame(
            self, parent, label, option_name, default_collapsed=0,
            leading_spacer=True, column_adj=True, row_spacing=None, margin_height=None,
            inside_form=False):
        self.create_guiOptionVar(option_name, defaultValue=default_collapsed)
        _mVar = self.__dict__['var_{0}'.format(option_name)]
        _frame_kw = dict(
            label=label,
            vis=True,
            collapse=_mVar.value,
            collapsable=True,
            enable=True,
            marginWidth=5,
            useTemplate='cgmUIHeaderTemplate',
            expandCommand=cgmGEN.Callback(_mVar.setValue, 0),
            collapseCommand=cgmGEN.Callback(_mVar.setValue, 1),
        )
        if margin_height is not None:
            _frame_kw['marginHeight'] = margin_height
        _frame = mUI.MelFrameLayout(parent, **_frame_kw)
        if inside_form:
            _inside = mUI.MelFormLayout(_frame, ut='cgmUISubTemplate')
        else:
            _col_kw = dict(useTemplate='cgmUISubTemplate', adj=column_adj)
            if row_spacing is not None:
                _col_kw['rowSpacing'] = row_spacing
            _inside = mUI.MelColumnLayout(_frame, **_col_kw)
            if leading_spacer:
                mUI.MelSpacer(_inside, h=_padding)
        return _frame, _inside

    def build_menus(self):
        self.uiMenu_FirstMenu = mUI.MelMenu(l='Setup', pmc=cgmGEN.Callback(self.buildMenu_first))

    def buildMenu_first(self):
        self.uiMenu_FirstMenu.clear()
        mUI.MelMenuItemDiv(self.uiMenu_FirstMenu)
        mUI.MelMenuItem(
            self.uiMenu_FirstMenu,
            l='Reload',
            ann='Reload Find Unknowns and perforce lib',
            c=lambda *a: mc.evalDeferred(self.reload, lp=True),
        )

    def reload(self):
        reload_tool()
        cgmGEN._reloadMod(__import__(__name__))
        super(ui, self).reload()

    @classmethod
    def showUI(cls):
        if cls.Exists():
            _ui = cls.Get()
            if not _ui_layout_current(_ui):
                try:
                    mc.deleteUI(cls.WINDOW_NAME)
                except Exception:
                    pass
                return cls()
            _ui.show(forceDefaultSize=False)
            uiFunc_refresh_connection_labels(_ui)
            uiFunc_refresh(_ui, force=False)
            uiFunc_load_unknown_from_cache(_ui)
            return _ui
        return cls()

    def build_layoutWrapper(self, parent):
        _main = mUI.MelFormLayout(parent, ut='cgmUITemplate')
        _top = mUI.MelColumnLayout(_main, adj=True)

        # --- Connection ---
        _frame_conn, _inside_conn = self._build_collapse_frame(
            _top, 'Connection', 'connectionFrameCollapse', 0)

        _row_conn = mUI.MelHSingleStretchLayout(
            _inside_conn, ut='cgmUISubTemplate', padding=0, expand=False)
        mUI.MelSpacer(_row_conn, w=1, h=1)
        self.uiLabel_connection = mUI.MelLabel(
            _row_conn,
            l='(click Refresh)',
            ut='cgmUIInstructionsTemplate',
            align='center',
            h=15,
        )
        _row_conn.setStretchWidget(self.uiLabel_connection)
        _row_conn.layout()

        _row_btns = mUI.MelHLayout(_inside_conn, ut='cgmUISubTemplate', padding=_padding)
        mUI.MelSpacer(_row_btns, w=_padding)
        mUI.MelButton(
            _row_btns,
            l='Print Log',
            ut='cgmUITemplate',
            ann='Print buffered P4 status report to Script Editor (Refresh first)',
            c=cgmGEN.Callback(uiFunc_print_log, self),
        )
        mUI.MelButton(
            _row_btns,
            l='Refresh',
            ut='cgmUITemplate',
            ann='Query p4 info and update status',
            c=cgmGEN.Callback(uiFunc_refresh, self, True),
        )
        mUI.MelSpacer(_row_btns, w=_padding)
        _row_btns.layout()

        mUI.MelSpacer(_inside_conn, h=_padding)

        # --- Status ---
        _frame_status, _inside_status = self._build_collapse_frame(
            _top, 'Status', 'statusFrameCollapse', 0,
            leading_spacer=False, column_adj=True, row_spacing=0, margin_height=2)

        _row_status = mUI.MelHSingleStretchLayout(
            _inside_status, ut='cgmUISubTemplate', padding=0, expand=False)
        mUI.MelSpacer(_row_status, w=1, h=1)
        self.uiLabel_status = mUI.MelLabel(
            _row_status,
            l='(click Refresh)',
            ut='cgmUIInstructionsTemplate',
            align='center',
            h=15,
        )
        _row_status.setStretchWidget(self.uiLabel_status)
        _row_status.layout()

        # --- Unknown Files (controls in frame; file rows scroll below) ---
        _frame_unknown, self.uiColumn_unknown = self._build_collapse_frame(
            _top, 'Unknown Files', 'unknownFrameCollapse', 0,
            leading_spacer=False, column_adj=True, row_spacing=0, margin_height=0)

        self.uiRow_unknown_ctrl = mUI.MelHSingleStretchLayout(
            self.uiColumn_unknown,
            ut='cgmUISubTemplate',
            padding=2,
            expand=True,
            h=_UNKNOWN_CTRL_ROW_H)
        mUI.MelSpacer(self.uiRow_unknown_ctrl, w=2)
        self.btn_unknown_query = mUI.MelIconButton(
            self.uiRow_unknown_ctrl,
            ann='Scan project content for local files not on depot (refreshes cache when present)',
            c=cgmGEN.Callback(uiFunc_query_unknown_files, self),
            **_icon_btn_kw('find_file.png', w=22, h=22),
        )
        self.btn_unknown_ext_all = mUI.MelButton(
            self.uiRow_unknown_ctrl,
            l='All',
            ut='cgmUITemplate',
            h=22,
            ann='Enable extension filters matching search; None clears all extension filters',
            c=cgmGEN.Callback(uiFunc_unknown_toggle_ext_all, self),
        )
        self.btn_unknown_ext_all.hide()
        self.uiLabel_unknown_count = mUI.MelLabel(
            self.uiRow_unknown_ctrl, l='Unknown (—)', ann='Unknown file count (checked / shown / total)')
        self.uiRow_unknown_ctrl.setStretchWidget(mUI.MelSeparator(self.uiRow_unknown_ctrl,))
        self.cb_unknown_master = mUI.MelCheckBox(
            self.uiRow_unknown_ctrl,
            value=1,
            ann='Check: visible files only. Uncheck: all files in the list.',
            changeCommand=cgmGEN.Callback(uiFunc_toggle_unknown_checks, self),
        )
        self.cb_unknown_master.hide()
        self.btn_unknown_batch_add = mUI.MelIconButton(
            self.uiRow_unknown_ctrl,
            ann='p4 add — checked files only, or all visible if none checked',
            c=cgmGEN.Callback(uiFunc_unknown_batch_add, self),
            **_icon_btn_kw('new_set.png', w=22, h=22),
        )
        self.btn_unknown_batch_add.hide()
        self.btn_unknown_batch_delete = mUI.MelIconButton(
            self.uiRow_unknown_ctrl,
            ann='Delete checked files from disk — or all visible if none checked',
            c=cgmGEN.Callback(uiFunc_unknown_batch_delete, self),
            **_icon_btn_kw('clear.png', w=22, h=22),
        )
        self.btn_unknown_batch_delete.hide()
        mUI.MelSpacer(self.uiRow_unknown_ctrl, w=2)
        self.uiRow_unknown_ctrl.layout()

        self.uiForm_unknown_ext = mUI.MelFormLayout(
            self.uiColumn_unknown, ut='cgmUISubTemplate', bgc=_UNKNOWN_EXT_FILTER_BGC)
        self.uiForm_unknown_ext.hide()

        self.uiForm_unknown_search = mUI.MelFormLayout(
            self.uiColumn_unknown, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor)
        _row_unknown_search = mUI.MelHSingleStretchLayout(
            self.uiForm_unknown_search,
            ut='cgmUIHeaderTemplate',
            padding=0,
            expand=True,
            h=_UNKNOWN_SEARCH_ROW_H)
        mUI.MelLabel(_row_unknown_search, l='Search:', w=50)
        self.tf_unknown_search = mUI.MelTextField(
            _row_unknown_search,
            ut='cgmUIReservedTemplate',
            h=20,
            ann='Filter loaded files — space-separated terms match basename or path')
        _row_unknown_search.setStretchWidget(self.tf_unknown_search)
        mUI.MelIconButton(
            _row_unknown_search,
            ann='Clear the field',
            image=os.path.join(_path_imageFolder, 'clear.png'),
            w=22,
            h=22,
            c=cgmGEN.Callback(uiFunc_unknown_clear_search, self),
        )
        self.tf_unknown_search(edit=True, tcc=cgmGEN.Callback(uiFunc_unknown_search_changed, self))
        _row_unknown_search.layout()
        self.uiForm_unknown_search(
            edit=True,
            attachForm=[
                (_row_unknown_search, 'top', 0),
                (_row_unknown_search, 'left', 0),
                (_row_unknown_search, 'right', 0),
            ],
        )
        self.uiForm_unknown_search.hide()

        self.uiRow_unknown_empty = mUI.MelHSingleStretchLayout(
            self.uiColumn_unknown, ut='cgmUISubTemplate', padding=0, expand=False)
        mUI.MelSpacer(self.uiRow_unknown_empty, w=1, h=1)
        self.uiLabel_unknown_empty = mUI.MelLabel(
            self.uiRow_unknown_empty,
            l='',
            ut='cgmUIInstructionsTemplate',
            align='center',
            h=15,
        )
        self.uiRow_unknown_empty.setStretchWidget(self.uiLabel_unknown_empty)
        self.uiRow_unknown_empty.layout()
        self.uiRow_unknown_empty.hide()

        self.uiScroll_unknown_files = mUI.MelScrollLayout(
            _main, ut='cgmUITemplate', childResizable=True)
        self.uiFrame_unknown = mUI.MelColumn(
            self.uiScroll_unknown_files, useTemplate='cgmUISubTemplate')

        self.uiRow_cgm_footer = cgmUI.add_cgmFooter(_main)
        _main(edit=True,
               af=[(_top, 'top', 0),
                   (_top, 'left', _edge_padding),
                   (_top, 'right', _edge_padding),
                   (self.uiScroll_unknown_files, 'left', _edge_padding),
                   (self.uiScroll_unknown_files, 'right', _edge_padding),
                   (self.uiRow_cgm_footer, 'left', 0),
                   (self.uiRow_cgm_footer, 'right', 0),
                   (self.uiRow_cgm_footer, 'bottom', 0)],
               ac=[(self.uiScroll_unknown_files, 'top', 0, _top),
                   (self.uiScroll_unknown_files, 'bottom', 2, self.uiRow_cgm_footer)],
               attachNone=[(self.uiRow_cgm_footer, 'top')])

    def post_init(self, *args, **kws):
        uiFunc_refresh_connection_labels(self)
        uiFunc_refresh(self, force=False)
        uiFunc_load_unknown_from_cache(self)


def uiFunc_status_buffer_matches(self):
    _dat = getattr(self, '_p4_status_dat', None)
    if not _dat:
        return False
    _user, _client = uiFunc_get_connection(self)
    return _dat.get('p4User') == _user and _dat.get('p4Client') == _client


def uiFunc_print_log(self):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        log.warning('Set User and Client first.')
        return
    if not getattr(self, '_p4_status_dat', None):
        log.warning('No status loaded — click Refresh first.')
        return
    if not uiFunc_status_buffer_matches(self):
        log.warning('User/client changed since last Refresh — click Refresh first.')
        return
    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    P4UTIL.log_status_report(self._p4_status_dat)


def uiFunc_set_connection_panel(self, lines):
    _parts = [str(_line).strip() for _line in (lines or []) if str(_line).strip()]
    _text = '\n'.join(_parts) if _parts else ''
    _line_count = max(1, len(_parts))
    self.uiLabel_connection(edit=True, l=_text, h=(13 * _line_count) + 2)


def uiFunc_refresh(self, force=False):
    uiFunc_refresh_connection_labels(self)
    _user, _client = uiFunc_get_connection(self)
    if force:
        P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)

    _dat = P4UTIL.query_connection(p4_user=_user, p4_client=_client, force=force)
    self._p4_status_dat = _dat

    _conn = _dat.get('connection') or {}

    if not _user or not _client:
        self._p4_status_dat = None
        uiFunc_set_status_panel(self, ['Set User and Client, then Refresh.'])
        return

    if not _dat.get('connected'):
        uiFunc_set_status_panel(self, [
            'Not connected',
            _dat.get('reason') or _conn.get('reason') or 'unknown',
        ])
        return

    _root = _conn.get('clientRoot') or '(not reported)'
    _stream = _conn.get('clientStream') or _conn.get('stream') or '(none)'
    uiFunc_set_status_panel(self, [
        'Connected as {0} @ {1}'.format(_conn.get('userName') or _user, _conn.get('clientName') or _client),
        'Root: {0}'.format(_root),
        'Stream: {0}'.format(_stream),
    ])


def _path_lookup_key(path):
    _norm = os.path.normpath(path) if path else None
    if not _norm:
        return None
    return os.path.normcase(_norm)


def _uiFunc_set_section_empty_state(self, frame_attr, empty_row_attr, label_attr, message):
    getattr(self, frame_attr).hide()
    getattr(self, label_attr)(edit=True, l=message)
    getattr(self, empty_row_attr).show()


def _uiFunc_set_section_content_state(self, frame_attr, empty_row_attr):
    getattr(self, empty_row_attr).hide()
    getattr(self, frame_attr).show()


def uiFunc_get_connection(self):
    return P4UTIL.resolve_connection()


def uiFunc_refresh_connection_labels(self):
    _user, _client = uiFunc_get_connection(self)
    _root, _mask, _err = uiFunc_resolve_project_unknown_scan()
    self._scan_root = _root
    self._scan_dir_mask = _mask

    if not _user or not _client:
        uiFunc_set_connection_panel(self, ['Set User and Client in cgmP4'])
        return

    _lines = [
        'User: {0}'.format(_user),
        'Client: {0}'.format(_client),
    ]
    if _err:
        _lines.append(_err)
    elif _root:
        _lines.append('Project: {0}'.format(_root))
        try:
            self.uiLabel_connection(edit=True, ann=_root)
        except Exception:
            pass
    else:
        _lines.append('Project: (not loaded)')
    uiFunc_set_connection_panel(self, _lines)


def uiFunc_resolve_project_unknown_scan():
    """Return (root_path, dir_mask, error_message)."""
    _user, _client = P4UTIL.resolve_connection()
    if not _user or not _client:
        return None, None, 'Set user/client in cgmP4 first.'

    import cgm.core.lib.path_utils as PATHUTIL
    import cgm.core.tools.Project as PROJECT

    _mDat = PATHUTIL.get_project_mDat()
    if not _mDat:
        return None, None, 'No project content path — load a project in Scene'
    try:
        _paths = _mDat.userPaths_get() or {}
    except Exception:
        _paths = {}
    _root = _paths.get('content')
    if not _root or not os.path.isdir(_root):
        return None, None, 'No project content path — load a project in Scene'
    return os.path.normpath(_root), PROJECT.project_dir_mask(_mDat), None


def _fstat_cache_warm_for_user_client(user, client):
    try:
        import cgm.core.lib.perforce_session as P4SESSION
        _store = P4SESSION._CACHE.get('fstat_by_path') or {}
    except Exception:
        return False
    for _key in _store:
        if len(_key) >= 2 and _key[0] == (user or '') and _key[1] == (client or ''):
            return True
    return False


def uiFunc_unknown_entry_ext_key(path):
    _base = os.path.basename(path or '')
    _root, _ext = os.path.splitext(_base)
    if not _ext:
        return _UNKNOWN_EXT_NONE
    return _ext.lower()


def uiFunc_unknown_collect_extensions(entries):
    _counts = {}
    for _entry in entries or []:
        _key = uiFunc_unknown_entry_ext_key(_entry.get('path'))
        _counts[_key] = _counts.get(_key, 0) + 1
    return _counts


def uiFunc_unknown_ext_checkbox_label(ext_key, count):
    if ext_key == _UNKNOWN_EXT_NONE:
        return '(none) ({0})'.format(count)
    return '{0} ({1})'.format(ext_key, count)


def uiFunc_unknown_ext_sort_key(item):
    _ext, _count = item
    if _ext == _UNKNOWN_EXT_NONE:
        return (1, -_count, _ext)
    return (0, -_count, _ext)


def uiFunc_unknown_get_saved_ext_enabled(self):
    try:
        _raw = (self.var_unknown_ext_enabled.getValue() or '').strip()
    except Exception:
        _raw = ''
    if not _raw or _raw == _UNKNOWN_EXT_ALL:
        return None
    return set(_part for _part in _raw.split('|') if _part)


def uiFunc_unknown_read_enabled_ext_keys(self):
    _ui = getattr(self, '_d_unknown_ext_ui', None) or {}
    if not _ui:
        return None
    _enabled = set()
    for _ext, _cb in _ui.items():
        try:
            if _cb.getValue():
                _enabled.add(_ext)
        except Exception:
            pass
    return _enabled


def uiFunc_unknown_save_ext_enabled(self, enabled_keys):
    _all = getattr(self, '_l_unknown_ext_keys', None) or []
    if not _all or len(enabled_keys) >= len(_all):
        try:
            self.var_unknown_ext_enabled.setValue(_UNKNOWN_EXT_ALL)
        except Exception:
            pass
        return
    try:
        self.var_unknown_ext_enabled.setValue('|'.join(sorted(enabled_keys)))
    except Exception:
        pass


def uiFunc_unknown_filter_entries(entries, enabled_keys):
    if not entries:
        return []
    if enabled_keys is None:
        return list(entries)
    if not enabled_keys:
        return []
    return [
        _entry for _entry in entries
        if uiFunc_unknown_entry_ext_key(_entry.get('path')) in enabled_keys
    ]


def uiFunc_unknown_layout_root(self):
    """Column layout stacks controls; file list scrolls separately — no form reattach."""
    return


def uiFunc_unknown_refresh_count_label(self, total=None, shown=None):
    if total is None:
        total = len(getattr(self, '_l_unknown_entries_all', []) or [])
    if shown is None:
        shown = len(getattr(self, '_l_unknown_entries', []) or [])
    if total <= 0:
        self.uiLabel_unknown_count(edit=True, l='Unknown (—)')
        return
    _checked = sum(
        1 for _entry in (getattr(self, '_l_unknown_entries', []) or [])
        if uiFunc_unknown_is_checked(self, _entry)
    )
    if shown == total and _checked == shown:
        self.uiLabel_unknown_count(edit=True, l='Unknown ({0})'.format(total))
    elif shown == total:
        self.uiLabel_unknown_count(edit=True, l='Unknown ({0}/{1})'.format(_checked, total))
    else:
        self.uiLabel_unknown_count(
            edit=True, l='Unknown ({0}/{1}/{2})'.format(_checked, shown, total))


def uiFunc_unknown_path_key(entry):
    return _path_lookup_key(entry.get('path') if isinstance(entry, dict) else entry)


def uiFunc_unknown_init_check_state(self, entries):
    _store = getattr(self, '_d_unknown_checked', None)
    if _store is None:
        self._d_unknown_checked = {}
        _store = self._d_unknown_checked
    for _entry in entries or []:
        _key = uiFunc_unknown_path_key(_entry)
        if _key and _key not in _store:
            _store[_key] = True


def uiFunc_unknown_is_checked(self, entry):
    _key = uiFunc_unknown_path_key(entry)
    if not _key:
        return True
    return getattr(self, '_d_unknown_checked', {}).get(_key, True)


def uiFunc_unknown_set_checked(self, entry, value):
    _key = uiFunc_unknown_path_key(entry)
    if not _key:
        return
    if getattr(self, '_d_unknown_checked', None) is None:
        self._d_unknown_checked = {}
    self._d_unknown_checked[_key] = bool(value)


def uiFunc_unknown_sync_visible_checks(self):
    _ui = getattr(self, '_d_unknown_ui', None) or {}
    for _cb, _idx in zip(_ui.get('file_cbs') or [], _ui.get('indices') or []):
        try:
            _entry = self._l_unknown_entries[_idx]
        except IndexError:
            continue
        _cb.setValue(uiFunc_unknown_is_checked(self, _entry))


def uiFunc_unknown_sync_master_check(self):
    _ui = getattr(self, '_d_unknown_ui', None) or {}
    _master = _ui.get('master_cb') or getattr(self, 'cb_unknown_master', None)
    if not _master or not self._l_unknown_entries:
        return
    try:
        _master.setValue(all(
            uiFunc_unknown_is_checked(self, _entry) for _entry in self._l_unknown_entries))
    except Exception:
        pass


def uiFunc_unknown_file_check_changed(self, path, *args):
    _entry = {'path': path}
    try:
        _cb_val = None
        _ui = getattr(self, '_d_unknown_ui', None) or {}
        for _cb, _idx in zip(_ui.get('file_cbs') or [], _ui.get('indices') or []):
            try:
                if self._l_unknown_entries[_idx].get('path') == path:
                    _cb_val = _cb.getValue()
                    break
            except IndexError:
                continue
        if _cb_val is None:
            return
        uiFunc_unknown_set_checked(self, _entry, _cb_val)
    except Exception:
        pass
    uiFunc_unknown_sync_master_check(self)
    uiFunc_unknown_refresh_count_label(self)


def uiFunc_unknown_search_filter_entries(entries, search_text):
    if not search_text or not str(search_text).strip():
        return list(entries or [])
    _terms = [(_term or '').lower() for _term in str(search_text).strip().split(' ') if _term]
    if not _terms:
        return list(entries or [])
    _out = []
    for _entry in entries or []:
        _path = _entry.get('path') or ''
        _hay = '{0} {1}'.format(os.path.basename(_path), _path).lower()
        if all(_term in _hay for _term in _terms):
            _out.append(_entry)
    return _out


def uiFunc_unknown_get_search_text(self):
    try:
        return (self.tf_unknown_search.getValue() or '').strip()
    except Exception:
        return ''


def uiFunc_unknown_clear_search_text(self):
    try:
        self.tf_unknown_search.setValue('')
    except Exception:
        pass


def uiFunc_unknown_search_changed(self, *args):
    uiFunc_refresh_unknown_list(self)


def uiFunc_unknown_clear_search(self, *args):
    uiFunc_unknown_clear_search_text(self)
    uiFunc_refresh_unknown_list(self)


def uiFunc_unknown_apply_list_filters(self, entries):
    _enabled = uiFunc_unknown_read_enabled_ext_keys(self)
    _ext_filtered = uiFunc_unknown_filter_entries(entries, _enabled)
    return uiFunc_unknown_search_filter_entries(_ext_filtered, uiFunc_unknown_get_search_text(self))


def uiFunc_unknown_update_ext_all_btn(self):
    _btn = getattr(self, 'btn_unknown_ext_all', None)
    _ui = getattr(self, '_d_unknown_ext_ui', None) or {}
    if not _btn or not _ui:
        return
    try:
        _all_checked = all(_cb.getValue() for _cb in _ui.values())
    except Exception:
        _all_checked = False
    _btn(edit=True, l='None' if _all_checked else 'All')


def uiFunc_unknown_toggle_ext_all(self, *args):
    _ui = getattr(self, '_d_unknown_ext_ui', None) or {}
    if not _ui:
        return
    try:
        _all_checked = all(_cb.getValue() for _cb in _ui.values())
    except Exception:
        _all_checked = False

    if _all_checked:
        for _cb in _ui.values():
            _cb.setValue(0)
    else:
        _all = getattr(self, '_l_unknown_entries_all', None) or []
        _search_filtered = uiFunc_unknown_search_filter_entries(
            _all, uiFunc_unknown_get_search_text(self))
        _exts = {
            uiFunc_unknown_entry_ext_key(_entry.get('path')) for _entry in _search_filtered
        }
        for _ext, _cb in _ui.items():
            _cb.setValue(1 if _ext in _exts else 0)
    uiFunc_unknown_ext_filter_changed(self)


def uiFunc_unknown_rebuild_ext_filters(self):
    _entries = getattr(self, '_l_unknown_entries_all', None) or []
    _counts = uiFunc_unknown_collect_extensions(_entries)

    self.uiForm_unknown_ext.clear()
    self._d_unknown_ext_ui = {}
    self._l_unknown_ext_keys = []

    if not _counts:
        self.uiForm_unknown_ext.hide()
        uiFunc_unknown_layout_root(self)
        return

    _saved = uiFunc_unknown_get_saved_ext_enabled(self)
    _sorted = sorted(_counts.items(), key=uiFunc_unknown_ext_sort_key)
    self._l_unknown_ext_keys = [_ext for _ext, _count in _sorted]

    _ncols = min(_UNKNOWN_EXT_GRID_COLS, max(1, len(_sorted)))
    _grid = mUI.MelGridLayout(
        self.uiForm_unknown_ext,
        ut='cgmUISubTemplate',
        numberOfColumns=_ncols,
        cellWidthHeight=_UNKNOWN_EXT_CELL_WH,
        columnsResizable=True,
        bgc=_UNKNOWN_EXT_FILTER_BGC,
    )
    for _ext, _count in _sorted:
        if _saved is None:
            _checked = True
        else:
            _checked = _ext in _saved
        _cb = mUI.MelCheckBox(
            _grid,
            label=uiFunc_unknown_ext_checkbox_label(_ext, _count),
            value=_checked,
            ann='Show or hide {0} files in the list'.format(_ext),
            changeCommand=cgmGEN.Callback(uiFunc_unknown_ext_filter_changed, self),
        )
        self._d_unknown_ext_ui[_ext] = _cb

    self.uiForm_unknown_ext(
        edit=True,
        attachForm=[
            (_grid, 'top', 0), (_grid, 'left', 0), (_grid, 'right', 0),
        ],
    )

    uiFunc_unknown_update_ext_all_btn(self)
    self.uiForm_unknown_ext.show()
    uiFunc_unknown_layout_root(self)


def uiFunc_unknown_update_ctrl_row(self, has_data=False, total=0, filtered=0):
    if not has_data:
        self.uiLabel_unknown_count(edit=True, l='Unknown (—)')
        self.uiForm_unknown_ext.hide()
        self.btn_unknown_ext_all.hide()
        self.uiForm_unknown_search.hide()
        self.cb_unknown_master.hide()
        self.btn_unknown_batch_delete.hide()
        self.btn_unknown_batch_add.hide()
        uiFunc_unknown_layout_root(self)
        return

    self.uiForm_unknown_ext.show()
    self.btn_unknown_ext_all.show()
    self.uiForm_unknown_search.show()
    self.cb_unknown_master.show()
    self.btn_unknown_batch_delete.show()
    self.btn_unknown_batch_add.show()
    uiFunc_unknown_refresh_count_label(self, total=total, shown=filtered)
    uiFunc_unknown_layout_root(self)


def uiFunc_unknown_ext_filter_changed(self, *args):
    _enabled = uiFunc_unknown_read_enabled_ext_keys(self)
    if _enabled is not None:
        uiFunc_unknown_save_ext_enabled(self, _enabled)
    uiFunc_unknown_update_ext_all_btn(self)
    uiFunc_refresh_unknown_list(self)


def uiFunc_refresh_unknown_list(self):
    _all = getattr(self, '_l_unknown_entries_all', None) or []
    _filtered = uiFunc_unknown_apply_list_filters(self, _all)

    self.uiFrame_unknown.clear()
    self._l_unknown_entries = list(_filtered)
    self._d_unknown_ui = {}

    _total = len(_all)
    _shown = len(_filtered)
    uiFunc_unknown_update_ctrl_row(self, has_data=_total > 0, total=_total, filtered=_shown)

    if not _all:
        _uiFunc_set_section_empty_state(
            self, 'uiScroll_unknown_files', 'uiRow_unknown_empty', 'uiLabel_unknown_empty',
            '(no unknown files)')
        uiFunc_unknown_layout_root(self)
        return

    if not _filtered:
        _uiFunc_set_section_content_state(self, 'uiScroll_unknown_files', 'uiRow_unknown_empty')
        _msg = '(no files match extension filter)'
        if uiFunc_unknown_get_search_text(self):
            _msg = '(no files match filter)'
        mUI.MelLabel(
            self.uiFrame_unknown,
            l=_msg,
            ut='cgmUIInstructionsTemplate',
            align='center',
        )
        self._d_unknown_ui = {'master_cb': self.cb_unknown_master, 'file_cbs': [], 'indices': []}
        uiFunc_unknown_layout_root(self)
        return

    _uiFunc_set_section_content_state(self, 'uiScroll_unknown_files', 'uiRow_unknown_empty')

    _file_cbs = []
    _indices = list(range(len(_filtered)))
    _inside = mUI.MelColumn(self.uiFrame_unknown, useTemplate='cgmUISubTemplate')
    for _idx, _entry in enumerate(_filtered):
        uiFunc_build_unknown_file_row(_inside, self, _entry, _idx, _file_cbs)

    self._d_unknown_ui = {
        'master_cb': self.cb_unknown_master,
        'file_cbs': _file_cbs,
        'indices': _indices,
    }
    uiFunc_unknown_sync_master_check(self)
    uiFunc_unknown_layout_root(self)


def uiFunc_toggle_unknown_checks(self, *args):
    _ui = getattr(self, '_d_unknown_ui', None) or {}
    _master = _ui.get('master_cb')
    if not _master:
        return
    _val = _master.getValue()
    if _val:
        for _entry in getattr(self, '_l_unknown_entries', []) or []:
            uiFunc_unknown_set_checked(self, _entry, True)
    else:
        for _entry in getattr(self, '_l_unknown_entries_all', []) or []:
            uiFunc_unknown_set_checked(self, _entry, False)
    uiFunc_unknown_sync_visible_checks(self)
    uiFunc_unknown_refresh_count_label(self)


def uiFunc_get_unknown_selection(self):
    _ui = getattr(self, '_d_unknown_ui', None) or {}
    _selected = []
    for _cb, _idx in zip(_ui.get('file_cbs') or [], _ui.get('indices') or []):
        try:
            _entry = self._l_unknown_entries[_idx]
        except IndexError:
            continue
        if not uiFunc_unknown_is_checked(self, _entry):
            continue
        _selected.append(_entry)
    return _ui, _selected


def uiFunc_build_unknown_file_row(parent, self, entry, idx, file_cbs):
    _bgc = _ROW_BGC_EVEN if MATH.is_even(idx) else _ROW_BGC_ODD
    _row = mUI.MelHSingleStretchLayout(parent, h=30, bgc=_bgc, padding=2)
    mUI.MelSpacer(_row, w=5)

    _path = entry.get('path') or '?'
    _cb = mUI.MelCheckBox(
        _row,
        value=uiFunc_unknown_is_checked(self, entry),
        changeCommand=cgmGEN.Callback(uiFunc_unknown_file_check_changed, self, _path),
    )
    file_cbs.append(_cb)

    _base = os.path.basename(_path)
    mUI.MelLabel(_row, l=_base, ann=_path)
    _row.setStretchWidget(mUI.MelLabel(_row, l=''))

    mUI.MelIconButton(
        _row,
        ann='Open folder — {0}'.format(_path),
        c=cgmGEN.Callback(uiFunc_unknown_row_open_dir, self, idx),
        **_icon_btn_kw('explorer_25.png', w=22, h=22),
    )
    mUI.MelIconButton(
        _row,
        ann='p4 add {0}'.format(_path),
        c=cgmGEN.Callback(uiFunc_unknown_row_add, self, idx),
        **_icon_btn_kw('new_set.png', w=22, h=22),
    )
    mUI.MelIconButton(
        _row,
        ann='Delete from disk — {0}'.format(_path),
        c=cgmGEN.Callback(uiFunc_unknown_row_delete, self, idx),
        **_icon_btn_kw('clear.png', w=22, h=22),
    )
    mUI.MelSpacer(_row, w=5)
    _row.layout()
    mUI.MelSeparator(parent, h=1)


def uiFunc_build_unknown_rows(self, unknown_dat):
    self._l_unknown_entries_all = []
    self._l_unknown_entries = []
    self._d_unknown_ui = {}
    self.uiFrame_unknown.clear()
    self._d_unknown_checked = {}
    uiFunc_unknown_clear_search_text(self)

    if unknown_dat is None:
        uiFunc_unknown_rebuild_ext_filters(self)
        uiFunc_unknown_update_ctrl_row(self, has_data=False)
        _uiFunc_set_section_empty_state(
            self, 'uiScroll_unknown_files', 'uiRow_unknown_empty', 'uiLabel_unknown_empty', '(not loaded)')
        uiFunc_unknown_layout_root(self)
        return

    if isinstance(unknown_dat, str):
        uiFunc_unknown_rebuild_ext_filters(self)
        uiFunc_unknown_update_ctrl_row(self, has_data=False)
        _uiFunc_set_section_empty_state(
            self, 'uiScroll_unknown_files', 'uiRow_unknown_empty', 'uiLabel_unknown_empty', unknown_dat)
        uiFunc_unknown_layout_root(self)
        return

    _entries = unknown_dat.get('entries') if isinstance(unknown_dat, dict) else unknown_dat
    if not _entries:
        uiFunc_unknown_rebuild_ext_filters(self)
        uiFunc_unknown_update_ctrl_row(self, has_data=False)
        _uiFunc_set_section_empty_state(
            self, 'uiScroll_unknown_files', 'uiRow_unknown_empty', 'uiLabel_unknown_empty',
            '(no unknown files)')
        uiFunc_unknown_layout_root(self)
        return

    self._l_unknown_entries_all = list(_entries)
    uiFunc_unknown_init_check_state(self, _entries)
    uiFunc_unknown_rebuild_ext_filters(self)
    uiFunc_refresh_unknown_list(self)


def uiFunc_load_unknown_from_cache(self):
    uiFunc_refresh_connection_labels(self)
    _root, _dir_mask, _err = uiFunc_resolve_project_unknown_scan()
    if _err:
        uiFunc_build_unknown_rows(self, _err)
        return
    self._scan_root = _root
    self._scan_dir_mask = _dir_mask
    _user, _client = uiFunc_get_connection(self)
    _cached = P4UTIL.get_cached_unknown_files(_root, p4_user=_user, p4_client=_client)
    if _cached is None:
        uiFunc_build_unknown_rows(self, '(click Query to scan project content)')
        return
    uiFunc_build_unknown_rows(self, _cached)


def uiFunc_query_unknown_files(self):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return log.warning('Set User and Client first.')

    _root, _dir_mask, _err = uiFunc_resolve_project_unknown_scan()
    if _err:
        uiFunc_build_unknown_rows(self, _err)
        return log.warning('P4 Find Unknowns: {0}'.format(_err))

    self._scan_root = _root
    self._scan_dir_mask = _dir_mask

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    _has_unknown_cache = P4UTIL.get_cached_unknown_files(_root, p4_user=_user, p4_client=_client) is not None
    _cache_warm = _fstat_cache_warm_for_user_client(_user, _client)
    _use_warm = (not _cache_warm) or _has_unknown_cache

    if _has_unknown_cache:
        P4UTIL.flush_unknown_cache_root(_root, p4_user=_user, p4_client=_client)
        log.info('P4 Find Unknowns: refreshing cache for {0}'.format(_root))
    elif not _cache_warm:
        log.info('P4 Find Unknowns: warming fstat cache for {0}'.format(_root))
    else:
        log.info('P4 Find Unknowns: scanning {0}'.format(_root))

    _progress = uiFunc_p4_progress_begin(
        'P4 Find Unknowns | refreshing cache...' if _has_unknown_cache else (
            'P4 Find Unknowns | warming cache...' if not _cache_warm else 'P4 Find Unknowns | starting...'),
        100)

    def _cancel_cb():
        if not _progress:
            return False
        try:
            return mc.progressBar(_progress, query=True, isCancelled=True)
        except Exception:
            return False

    def _collect_progress_cb(processed, total, current_path):
        if uiFunc_p4_progress_update(
                _progress,
                status='P4 Find Unknowns | {0}/{1} | {2}'.format(
                    processed, total, os.path.basename(current_path or _root)),
                progress=processed,
                max_value=max(total, 1)):
            return True
        return False

    if _use_warm:
        def _warm_progress_cb(files_cached, files_total, current_path, dirs_done=0, dir_total=0, current_dir=None):
            _total = files_total if files_total else max(files_cached, 1)
            if uiFunc_p4_progress_update(
                    _progress,
                    status='P4 Find Unknowns | cache {0}/{1} | {2}'.format(
                        files_cached, _total, os.path.basename(current_path or _root)),
                    progress=files_cached,
                    max_value=_total):
                return True
            return False

        _warm = P4UTIL.warm_fstat_cache_tree(
            _root,
            p4_user=_user,
            p4_client=_client,
            dir_mask=_dir_mask,
            progress_cb=_warm_progress_cb,
            cancel_cb=_cancel_cb,
        )
        if _warm.get('cancelled'):
            uiFunc_p4_progress_end(_progress)
            return log.warning('P4 Find Unknowns: cancelled')
        if _warm.get('error'):
            uiFunc_p4_progress_end(_progress)
            return log.error('P4 Find Unknowns cache failed: {0}'.format(_warm.get('error')))

        _cached = P4UTIL.get_cached_unknown_files(_root, p4_user=_user, p4_client=_client)
        uiFunc_p4_progress_end(_progress)
        if _cached is not None:
            log.info(
                'P4 Find Unknowns: {0} file(s) under {1} (cache warmed)'.format(
                    _cached.get('fileCount', 0), _root))
            uiFunc_build_unknown_rows(self, _cached)
            return

    _res = P4UTIL.collect_unknown_files(
        _root,
        p4_user=_user,
        p4_client=_client,
        dir_mask=_dir_mask,
        depot_paths=None,
        scope=_PROJECT_SCOPE,
        progress_cb=_collect_progress_cb,
        cancel_cb=_cancel_cb,
    )
    uiFunc_p4_progress_end(_progress)

    if _res.get('cancelled'):
        return log.warning('P4 Find Unknowns: cancelled')
    if _res.get('error'):
        return log.error('P4 Find Unknowns failed: {0}'.format(_res.get('error')))

    log.info('P4 Find Unknowns: {0} file(s) under {1}'.format(_res.get('fileCount', 0), _root))
    uiFunc_build_unknown_rows(self, _res)


def uiFunc_prompt_add_changelist(entry_count, user, client):
    _preview = ''
    if entry_count == 1:
        _preview = '\n\n1 file selected.'
    elif entry_count > 1:
        _preview = '\n\n{0} files selected.'.format(entry_count)

    _result = uiFunc_prompt_changelist_target(
        title='Add to Perforce',
        message='Add to which changelist?{0}'.format(_preview),
        user=user,
        client=client,
        status_dat=None,
    )
    if _result is False:
        return False
    if _result == 'new':
        _desc = cgmUI.uiPrompt_getValue(
            title='New changelist',
            message='Description for the new changelist:',
            style='text',
        )
        if _desc is None:
            return False
        _desc = _desc.strip()
        if not _desc:
            log.warning('P4 Add: description required for new changelist')
            return False

        _create = P4UTIL.create_pending_change(_desc, p4_user=user, p4_client=client)
        if not _create.get('ok'):
            log.error('P4 Add: create changelist failed: {0}'.format(_create.get('stderr') or 'unknown'))
            return False

        _change = _create.get('change')
        log.info('P4 Add: created changelist {0}'.format(_change))
        return _change
    return _result


def uiFunc_unknown_add_paths(self, entries):
    if not entries:
        return log.warning('P4 Add: no files selected')
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return log.warning('Set User and Client first.')

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)

    _changelist = uiFunc_prompt_add_changelist(len(entries), _user, _client)
    if _changelist is False:
        return log.info('P4 Add: cancelled')

    _cl_label = 'default changelist'
    if _changelist is not None:
        _cl_label = 'changelist {0}'.format(_changelist)
    log.info('P4 Add: adding {0} file(s) to {1}'.format(len(entries), _cl_label))

    _progress = uiFunc_p4_progress_begin('P4 Add | starting...', len(entries))
    _failures = []
    _added = []

    for _i, _entry in enumerate(entries, 1):
        if uiFunc_p4_progress_update(
                _progress,
                status='P4 Add | {0}/{1}'.format(_i, len(entries)),
                progress=_i,
                max_value=len(entries)):
            log.warning('P4 Add: cancelled')
            break
        _path = _entry.get('path')
        if not _path:
            continue
        _res = P4UTIL.add(
            _path, p4_user=_user, p4_client=_client, changelist=_changelist)
        if _res.get('ok'):
            log.info('Added: {0}'.format(_path))
            _added.append(_path)
        else:
            _failures.append('{0}: {1}'.format(_path, _res.get('stderr') or 'unknown'))

    uiFunc_p4_progress_end(_progress)

    if _added:
        _drop = {_path_lookup_key(p) for p in _added}
        self._l_unknown_entries_all = [
            _e for _e in getattr(self, '_l_unknown_entries_all', [])
            if _path_lookup_key(_e.get('path')) not in _drop
        ]
        for _path in _added:
            uiFunc_unknown_set_checked(self, {'path': _path}, False)
        uiFunc_unknown_rebuild_ext_filters(self)
        uiFunc_refresh_unknown_list(self)
        log.info('P4 Add: refresh cgmP4 Opened Files to see added files.')

    if _failures:
        log.error('Some adds failed:\n{0}'.format('\n'.join(_failures)))


def uiFunc_unknown_row_open_dir(self, idx, *args):
    try:
        _entry = self._l_unknown_entries[idx]
    except IndexError:
        return
    _path = _entry.get('path') or ''
    _dir = os.path.dirname(os.path.normpath(_path)) if _path else ''
    if _dir and os.path.isdir(_dir):
        os.startfile(_dir)
        return
    log.warning('Path not found - {0}'.format(_dir or _path or '?'))


def uiFunc_unknown_row_add(self, idx, *args):
    try:
        _entry = self._l_unknown_entries[idx]
    except IndexError:
        return
    uiFunc_unknown_add_paths(self, [_entry])


def uiFunc_unknown_batch_add(self, *args):
    _ui, _selected = uiFunc_get_unknown_selection(self)
    if not _ui:
        return
    if _selected:
        _targets = _selected
    else:
        _targets = [
            _e for _e in self._l_unknown_entries
            if uiFunc_unknown_is_checked(self, _e)
        ]
        if not _targets:
            _targets = list(self._l_unknown_entries)
    uiFunc_unknown_add_paths(self, _targets)


def uiFunc_unknown_resolve_delete_targets(self):
    _ui, _selected = uiFunc_get_unknown_selection(self)
    if not _ui:
        return []
    if _selected:
        return _selected
    _targets = [
        _e for _e in self._l_unknown_entries
        if uiFunc_unknown_is_checked(self, _e)
    ]
    if not _targets:
        _targets = list(self._l_unknown_entries)
    return _targets


def uiFunc_unknown_remove_disk_file(path):
    """Delete a local file; clear read-only (P4 workspace) on Windows before retry."""
    try:
        os.remove(path)
        return True, None
    except OSError as err:
        if getattr(err, 'winerror', None) != 5 and err.errno not in (13, 1):
            return False, err
        try:
            os.chmod(path, stat.S_IWRITE)
            os.remove(path)
            return True, None
        except OSError as err2:
            return False, err2


def uiFunc_unknown_delete_paths(self, entries):
    if not entries:
        return log.warning('Delete: no files selected')

    _paths = []
    for _entry in entries:
        _path = (_entry.get('path') if isinstance(_entry, dict) else _entry) or ''
        _path = os.path.normpath(_path)
        if _path and os.path.isfile(_path):
            _paths.append(_path)
    if not _paths:
        return log.warning('Delete: no valid files selected')

    _scan_root = getattr(self, '_scan_root', None)
    if _scan_root:
        _root_norm = os.path.normpath(_scan_root)
        _safe = []
        for _p in _paths:
            try:
                if os.path.commonpath([_root_norm, os.path.normpath(_p)]) == _root_norm:
                    _safe.append(_p)
            except ValueError:
                pass
        _paths = _safe
    if not _paths:
        return log.warning('Delete: selected files are outside the project scan root')

    if len(_paths) == 1:
        _preview = _paths[0]
    elif len(_paths) <= 5:
        _preview = '\n'.join(_paths)
    else:
        _preview = '\n'.join(_paths[:5]) + '\n... and {0} more'.format(len(_paths) - 5)

    _confirm = mc.confirmDialog(
        title='Delete Local Files',
        message='Permanently delete from disk?\n\n{0}'.format(_preview),
        button=['Delete', 'Cancel'],
        defaultButton='Cancel',
        cancelButton='Cancel',
        dismissString='Cancel',
    )
    if _confirm != 'Delete':
        return log.info('Delete: cancelled')

    _user, _client = uiFunc_get_connection(self)
    _progress = uiFunc_p4_progress_begin('Delete | starting...', len(_paths))
    _deleted = []
    _failures = []

    for _i, _path in enumerate(_paths, 1):
        if uiFunc_p4_progress_update(
                _progress,
                status='Delete | {0}/{1} | {2}'.format(_i, len(_paths), os.path.basename(_path)),
                progress=_i,
                max_value=len(_paths)):
            log.warning('Delete: cancelled')
            break
        _ok, _err = uiFunc_unknown_remove_disk_file(_path)
        if _ok:
            log.info('Deleted: {0}'.format(_path))
            _deleted.append(_path)
        else:
            _failures.append('{0}: {1}'.format(_path, _err))

    uiFunc_p4_progress_end(_progress)

    if _deleted:
        P4UTIL.invalidate_unknown_paths(_deleted, p4_user=_user, p4_client=_client)
        P4UTIL.invalidate_fstat_paths(_deleted, p4_user=_user, p4_client=_client)
        _drop = {_path_lookup_key(_p) for _p in _deleted}
        self._l_unknown_entries_all = [
            _e for _e in getattr(self, '_l_unknown_entries_all', [])
            if _path_lookup_key(_e.get('path')) not in _drop
        ]
        for _path in _deleted:
            uiFunc_unknown_set_checked(self, {'path': _path}, False)
        uiFunc_unknown_rebuild_ext_filters(self)
        uiFunc_refresh_unknown_list(self)

    if _failures:
        log.error('Some deletes failed:\n{0}'.format('\n'.join(_failures)))


def uiFunc_unknown_row_delete(self, idx, *args):
    try:
        _entry = self._l_unknown_entries[idx]
    except IndexError:
        return
    uiFunc_unknown_delete_paths(self, [_entry])


def uiFunc_unknown_batch_delete(self, *args):
    _targets = uiFunc_unknown_resolve_delete_targets(self)
    uiFunc_unknown_delete_paths(self, _targets)
