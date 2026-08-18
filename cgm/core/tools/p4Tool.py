"""
------------------------------------------
p4Tool : cgm.core.tools
Perforce connection UI — prefs, status, opened files, path query.
------------------------------------------
"""
import logging
import os

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

import maya.cmds as mc

import cgm.core.classes.GuiFactory as cgmUI
import cgm.core.cgm_Meta as cgmMeta
import cgm.core.cgm_General as cgmGEN
import cgm.core.lib.math_utils as MATH
import cgm.core.lib.perforce as P4UTIL

mUI = cgmUI.mUI

__version__ = cgmGEN.__RELEASESTRING
__toolname__ = 'cgmP4'
_padding = 5
_edge_padding = 5
_ROW_BGC_EVEN = [.75, .75, .75]
_ROW_BGC_ODD = [.65, .65, .65]
_OPENED_CL_HEADER_BGC = cgmUI.guiHeaderColor
_SHELVED_CL_HEADER_BGC = [.62, .68, .78]


def reload_dependencies():
    """Reload P4 session cache + perforce lib (Setup → Reload)."""
    import cgm.core.lib.perforce_session as P4SESSION
    cgmGEN._reloadMod(P4SESSION)
    cgmGEN._reloadMod(P4UTIL)


class ui(cgmUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    WINDOW_NAME = '{0}_ui'.format(__toolname__)
    WINDOW_TITLE = '{1} - {0}'.format(__version__, __toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = False
    DEFAULT_SIZE = 600, 580
    TOOLNAME = '{0}.ui'.format(__toolname__)

    def insert_init(self, *args, **kws):
        self.var_p4_user = cgmMeta.cgmOptionVar(P4UTIL.OPT_P4_USER, varType='string', defaultValue='')
        self.var_p4_client = cgmMeta.cgmOptionVar(P4UTIL.OPT_P4_CLIENT, varType='string', defaultValue='')
        self._l_opened_entries = []
        self._p4_status_dat = None
        self._d_opened_cl_ui = {}
        self._l_shelved_entries = []
        self._d_shelved_cl_ui = {}

    def build_menus(self):
        self.uiMenu_FirstMenu = mUI.MelMenu(l='Setup', pmc=cgmGEN.Callback(self.buildMenu_first))

    def buildMenu_first(self):
        self.uiMenu_FirstMenu.clear()
        mUI.MelMenuItemDiv(self.uiMenu_FirstMenu)
        mUI.MelMenuItem(
            self.uiMenu_FirstMenu,
            l='Reload',
            ann='Reload p4Tool and perforce lib',
            c=lambda *a: mc.evalDeferred(self.reload, lp=True),
        )
        mUI.MelMenuItem(
            self.uiMenu_FirstMenu,
            l='Reset',
            ann='Reload p4Tool and perforce lib',
            c=lambda *a: mc.evalDeferred(self.reload, lp=True),
        )

    def reload(self):
        reload_dependencies()
        cgmGEN._reloadMod(__import__(__name__))
        super(ui, self).reload()

    @classmethod
    def showUI(cls):
        """Reuse existing cgmP4 window when still open."""
        if cls.Exists():
            _ui = cls.Get()
            _ui.show(forceDefaultSize=False)
            return _ui
        return cls()

    def _build_collapse_frame(
            self, parent, label, option_name, default_collapsed=0,
            leading_spacer=True, column_adj=True, row_spacing=None, margin_height=None):
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
        _col_kw = dict(useTemplate='cgmUISubTemplate', adj=column_adj)
        if row_spacing is not None:
            _col_kw['rowSpacing'] = row_spacing
        _inside = mUI.MelColumnLayout(_frame, **_col_kw)
        if leading_spacer:
            mUI.MelSpacer(_inside, h=_padding)
        return _frame, _inside

    def build_layoutWrapper(self, parent):
        _main = mUI.MelFormLayout(parent, ut='cgmUITemplate')
        _scroll = mUI.MelScrollLayout(_main, ut='cgmUITemplate')

        # --- Connection ---
        _frame_conn, _inside_conn = self._build_collapse_frame(
            _scroll, 'Connection', 'connectionFrameCollapse', 0)

        _row_user = mUI.MelHSingleStretchLayout(_inside_conn, ut='cgmUISubTemplate', padding=_padding)
        mUI.MelSpacer(_row_user, w=_padding)
        mUI.MelLabel(_row_user, l='User', w=50)
        self.tf_p4_user = mUI.MelTextField(_row_user, text=self.var_p4_user.getValue() or '', ann='P4USER')
        _row_user.setStretchWidget(self.tf_p4_user)
        mUI.MelSpacer(_row_user, w=_padding)
        _row_user.layout()

        _row_client = mUI.MelHSingleStretchLayout(_inside_conn, ut='cgmUISubTemplate', padding=_padding)
        mUI.MelSpacer(_row_client, w=_padding)
        mUI.MelLabel(_row_client, l='Client', w=50)
        self.tf_p4_client = mUI.MelTextField(
            _row_client, text=self.var_p4_client.getValue() or '', ann='P4CLIENT workspace name')
        _row_client.setStretchWidget(self.tf_p4_client)
        mUI.MelSpacer(_row_client, w=_padding)
        _row_client.layout()

        _row_btns = mUI.MelHLayout(_inside_conn, ut='cgmUISubTemplate', padding=_padding)
        mUI.MelSpacer(_row_btns, w=_padding)
        mUI.MelButton(
            _row_btns,
            l='Save',
            ut='cgmUITemplate',
            ann='Save user/client to cgm optionVars',
            c=cgmGEN.Callback(uiFunc_save, self),
        )
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
        mUI.MelButton(
            _row_btns,
            l='Sync Workspace',
            ut='cgmUITemplate',
            ann='p4 sync entire client workspace to head',
            c=cgmGEN.Callback(uiFunc_sync_workspace, self),
        )
        mUI.MelSpacer(_row_btns, w=_padding)
        _row_btns.layout()

        mUI.MelSpacer(_inside_conn, h=_padding)

        # --- Status ---
        _frame_status, _inside_status = self._build_collapse_frame(
            _scroll, 'Status', 'statusFrameCollapse', 0,
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

        # --- Opened Files ---
        _frame_opened, _inside_opened = self._build_collapse_frame(
            _scroll, 'Opened Files', 'openedFrameCollapse', 0,
            leading_spacer=False, column_adj=True, row_spacing=0, margin_height=2)

        _row_opened_empty = mUI.MelHSingleStretchLayout(
            _inside_opened, ut='cgmUISubTemplate', padding=0, expand=False)
        mUI.MelSpacer(_row_opened_empty, w=1, h=1)
        self.uiLabel_opened_empty = mUI.MelLabel(
            _row_opened_empty,
            l='',
            ut='cgmUIInstructionsTemplate',
            align='center',
            h=15,
        )
        _row_opened_empty.setStretchWidget(self.uiLabel_opened_empty)
        _row_opened_empty.layout()
        self.uiRow_opened_empty = _row_opened_empty
        self.uiRow_opened_empty.hide()

        self.uiFrame_opened = mUI.MelColumn(_inside_opened, useTemplate='cgmUISubTemplate')
        mUI.MelSpacer(_inside_opened, h=_padding)

        # --- Shelved Files ---
        _frame_shelved, _inside_shelved = self._build_collapse_frame(
            _scroll, 'Shelved Files', 'shelvedFrameCollapse', 0,
            leading_spacer=False, column_adj=True, row_spacing=0, margin_height=2)

        _row_shelved_empty = mUI.MelHSingleStretchLayout(
            _inside_shelved, ut='cgmUISubTemplate', padding=0, expand=False)
        mUI.MelSpacer(_row_shelved_empty, w=1, h=1)
        self.uiLabel_shelved_empty = mUI.MelLabel(
            _row_shelved_empty,
            l='',
            ut='cgmUIInstructionsTemplate',
            align='center',
            h=15,
        )
        _row_shelved_empty.setStretchWidget(self.uiLabel_shelved_empty)
        _row_shelved_empty.layout()
        self.uiRow_shelved_empty = _row_shelved_empty
        self.uiRow_shelved_empty.hide()

        self.uiFrame_shelved = mUI.MelColumn(_inside_shelved, useTemplate='cgmUISubTemplate')
        mUI.MelSpacer(_inside_shelved, h=_padding)

        # --- Path Query ---
        _frame_path, _inside_path = self._build_collapse_frame(
            _scroll, 'Path Query', 'pathFrameCollapse', 0)

        _row_path = mUI.MelHSingleStretchLayout(_inside_path, ut='cgmUISubTemplate', padding=_padding)
        mUI.MelSpacer(_row_path, w=_padding)
        mUI.MelLabel(_row_path, l='Path', w=50)
        self.tf_query_path = mUI.MelTextField(_row_path, text='', ann='Absolute disk path to query')
        _row_path.setStretchWidget(self.tf_query_path)
        mUI.MelButton(
            _row_path, l='Scene', ut='cgmUITemplate',
            ann='Use current Maya scene path',
            c=cgmGEN.Callback(uiFunc_use_scene_path, self),
        )
        mUI.MelButton(
            _row_path, l='Query', ut='cgmUITemplate',
            ann='Check workspace membership and file status',
            c=cgmGEN.Callback(uiFunc_query_path, self),
        )
        mUI.MelButton(
            _row_path, l='Checkout', ut='cgmUITemplate',
            ann='p4 edit or p4 add for this path',
            c=cgmGEN.Callback(uiFunc_checkout_path, self),
        )
        mUI.MelSpacer(_row_path, w=_padding)
        _row_path.layout()

        self.uiLabel_path = mUI.MelLabel(
            _inside_path, l='', ut='cgmUIInstructionsTemplate', align='left')
        mUI.MelSpacer(_inside_path, h=_padding)

        _row_footer = cgmUI.add_cgmFooter(_main)
        _main(edit=True,
               af=[(_scroll, 'top', 0),
                   (_scroll, 'left', _edge_padding),
                   (_scroll, 'right', _edge_padding),
                   (_row_footer, 'left', 0),
                   (_row_footer, 'right', 0),
                   (_row_footer, 'bottom', 0)],
               ac=[(_scroll, 'bottom', 2, _row_footer)],
               attachNone=[(_row_footer, 'top')])

    def post_init(self, *args, **kws):
        uiFunc_clear_path_query(self)
        uiFunc_refresh(self)


def uiFunc_get_connection(self):
    return (
        (self.tf_p4_user.getValue() or '').strip(),
        (self.tf_p4_client.getValue() or '').strip(),
    )


def uiFunc_clear_path_query(self):
    """Reset Path Query field and result label."""
    try:
        self.tf_query_path(edit=True, text='')
    except Exception:
        pass
    try:
        self.uiLabel_path(edit=True, l='')
    except Exception:
        pass


def uiFunc_save(self):
    _user, _client = uiFunc_get_connection(self)
    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    log.info('Saved P4 prefs: user={0} client={1}'.format(_user, _client))


def uiFunc_set_status_panel(self, lines):
    _parts = [str(_line).strip() for _line in (lines or []) if str(_line).strip()]
    _text = '\n'.join(_parts) if _parts else ''
    _line_count = max(1, len(_parts))
    self.uiLabel_status(edit=True, l=_text, h=(13 * _line_count) + 2)


def _shelved_change_key(change):
    return str(change)


def _shelf_entry_path(entry):
    return entry.get('depotFile') or entry.get('clientFile') or '?'


def _uiFunc_set_section_empty_state(self, frame_attr, empty_row_attr, label_attr, message):
    """Show a full-width centered empty message (Status panel pattern)."""
    getattr(self, frame_attr).hide()
    getattr(self, label_attr)(edit=True, l=message)
    getattr(self, empty_row_attr).show()


def _uiFunc_set_section_content_state(self, frame_attr, empty_row_attr):
    getattr(self, empty_row_attr).hide()
    getattr(self, frame_attr).show()


def uiFunc_toggle_shelf_cl_checks(self, change_key, *args):
    _ui = self._d_shelved_cl_ui.get(_shelved_change_key(change_key))
    if not _ui:
        return
    _val = _ui['master_cb'].getValue()
    for _cb in _ui['file_cbs']:
        _cb.setValue(_val)


def uiFunc_get_shelf_cl_selection(self, change_key):
    _ui = self._d_shelved_cl_ui.get(_shelved_change_key(change_key))
    if not _ui:
        return None, []
    _selected_paths = []
    for _cb, _idx in zip(_ui['file_cbs'], _ui['indices']):
        if not _cb.getValue():
            continue
        try:
            _entry = self._l_shelved_entries[_idx]
        except IndexError:
            continue
        _path = _shelf_entry_path(_entry)
        if _path and _path != '?':
            _selected_paths.append(_path)
    return _ui, _selected_paths


def _opened_change_key(change):
    _change_str = str(change).lower() if change is not None else 'default'
    return _change_str if _change_str not in ('',) else 'default'


def uiFunc_toggle_cl_checks(self, change_key, *args):
    _ui = self._d_opened_cl_ui.get(_opened_change_key(change_key))
    if not _ui:
        return
    _val = _ui['master_cb'].getValue()
    for _cb in _ui['file_cbs']:
        _cb.setValue(_val)


def _opened_entry_label_path(entry):
    return entry.get('clientFile') or entry.get('depotFile') or '?'


def uiFunc_get_cl_selection(self, change_key):
    _ui = self._d_opened_cl_ui.get(_opened_change_key(change_key))
    if not _ui:
        return None, []
    _selected_entries = []
    for _cb, _idx in zip(_ui['file_cbs'], _ui['indices']):
        if not _cb.getValue():
            continue
        try:
            _entry = self._l_opened_entries[_idx]
        except IndexError:
            continue
        _selected_entries.append(_entry)
    return _ui, _selected_entries


def _format_cl_entry_preview(entries, max_lines=8):
    return _format_cl_path_preview(
        [_opened_entry_label_path(_e) for _e in (entries or [])],
        max_lines=max_lines,
    )


def uiFunc_p4_progress_begin(status, max_steps=1):
    try:
        return cgmUI.doStartMayaProgressBar(
            stepMaxValue=max(int(max_steps), 1),
            statusMessage=status,
            interruptableState=True,
        )
    except Exception:
        return None


def uiFunc_p4_progress_update(progress_bar, status=None, progress=None, max_value=None):
    if not progress_bar:
        return False
    try:
        if mc.progressBar(progress_bar, query=True, isCancelled=True):
            return True
        _kw = {}
        if status is not None:
            _kw['status'] = status
        if progress is not None:
            _kw['progress'] = progress
        if max_value is not None:
            _kw['maxValue'] = max(int(max_value), 1)
        cgmUI.progressBar_set(progress_bar, **_kw)
        if progress in (1, max_value) or (progress and int(progress) % 5 == 0):
            try:
                mc.refresh()
            except Exception:
                pass
    except Exception:
        pass
    return False


def uiFunc_p4_progress_end(progress_bar):
    if not progress_bar:
        return
    try:
        cgmUI.progressBar_end(progress_bar)
    except Exception:
        try:
            cgmUI.doEndMayaProgressBar(progress_bar)
        except Exception:
            pass


def uiFunc_p4_submit_progress_cb(progress_bar):
    def _cb(step, total, status):
        return uiFunc_p4_progress_update(
            progress_bar, status=status, progress=step, max_value=total)
    return _cb


def uiFunc_submit_progress_max_steps(change, opened_entries=None, file_count=None):
    """Progress steps for Maya bar — default partial multi-file uses create/reopen/submit."""
    _change_str = str(change).lower() if change is not None else 'default'
    _count = len(opened_entries or [])
    if not _count and file_count:
        _count = int(file_count)
    if _change_str in ('default', '') and _count > 1:
        return 3
    return 1


def uiFunc_run_submit_paths(change, description, opened_entries, user, client):
    _max_steps = uiFunc_submit_progress_max_steps(change, opened_entries=opened_entries)
    _progress = uiFunc_p4_progress_begin('P4 Submit | starting...', _max_steps)
    _cb = uiFunc_p4_submit_progress_cb(_progress) if _progress else None
    try:
        return P4UTIL.submit_paths(
            None, change=change, description=description,
            opened_entries=opened_entries,
            p4_user=user, p4_client=client, progress_cb=_cb)
    finally:
        uiFunc_p4_progress_end(_progress)


def uiFunc_run_submit_change(change, description, user, client, file_count=None):
    _max_steps = uiFunc_submit_progress_max_steps(change, file_count=file_count)
    _progress = uiFunc_p4_progress_begin('P4 Submit | starting...', _max_steps)
    _cb = uiFunc_p4_submit_progress_cb(_progress) if _progress else None
    try:
        return P4UTIL.submit_change(
            change, description=description,
            p4_user=user, p4_client=client, progress_cb=_cb)
    finally:
        uiFunc_p4_progress_end(_progress)


def uiFunc_log_submit_result(res, success_msg, fail_prefix='Submit failed'):
    if res.get('cancelled'):
        log.warning('Submit cancelled')
        return
    if res.get('ok'):
        log.info(success_msg)
    else:
        log.error('{0}: {1}'.format(fail_prefix, res.get('stderr') or 'unknown'))


def _format_cl_path_preview(paths, max_lines=8):
    _preview = '\n'.join(paths[:max_lines])
    if len(paths) > max_lines:
        _preview += '\n...'
    return _preview


def uiFunc_prompt_change_description(title, message, change, user, client):
    _default = P4UTIL.query_change_description(change, p4_user=user, p4_client=client) or None
    _desc = cgmUI.uiPrompt_getValue(
        title=title,
        message=message,
        text=_default,
        style='text',
    )
    if _desc is None:
        return None
    _desc = _desc.strip()
    if not _desc:
        log.warning('{0}: description required'.format(title))
        return None
    return _desc


def uiFunc_build_opened_file_row(parent, self, entry, idx, file_cbs):
    _bgc = _ROW_BGC_EVEN if MATH.is_even(idx) else _ROW_BGC_ODD
    _row = mUI.MelHSingleStretchLayout(parent, h=30, bgc=_bgc, padding=2)
    mUI.MelSpacer(_row, w=5)

    _cb = mUI.MelCheckBox(_row, value=1)
    file_cbs.append(_cb)

    _change = entry.get('change', 'default')
    _action = entry.get('action', '?')
    _rev = entry.get('rev', '?')
    _path = entry.get('clientFile') or entry.get('depotFile') or '?'
    _base = os.path.basename(_path)
    _label = '{0} {1}#{2}'.format(_base, _action, _rev)

    mUI.MelLabel(_row, l=_label, ann=_path)
    _row.setStretchWidget(mUI.MelLabel(_row, l=''))

    mUI.MelButton(
        _row, l='Revert', bgc=cgmUI.guiButtonColor,
        ann='p4 revert {0}'.format(_path),
        c=cgmGEN.Callback(uiFunc_row_revert, self, idx),
    )
    mUI.MelButton(
        _row, l='Submit', bgc=cgmUI.guiButtonColor,
        ann='p4 submit {0}'.format(_path),
        c=cgmGEN.Callback(uiFunc_row_submit, self, idx),
    )
    mUI.MelButton(
        _row, l='Shelve', bgc=cgmUI.guiButtonColor,
        ann='p4 shelve {0}'.format(_path),
        c=cgmGEN.Callback(uiFunc_row_shelve, self, idx),
    )
    mUI.MelSpacer(_row, w=5)
    _row.layout()
    mUI.MelSeparator(parent, h=1)


def uiFunc_build_opened_changelist_section(self, parent, grp, start_idx):
    _change_key = _opened_change_key(grp['change'])
    _header = _OPENED_CL_HEADER_BGC
    _file_cbs = []
    _indices = []

    _row = mUI.MelHSingleStretchLayout(parent, bgc=_header, padding=2)
    _master_cb = mUI.MelCheckBox(
        _row,
        value=1,
        ann='Select all files in this changelist for R / S / Sh',
        changeCommand=cgmGEN.Callback(uiFunc_toggle_cl_checks, self, _change_key),
    )
    mUI.MelSpacer(_row, w=5)

    _sub_column = mUI.MelColumnLayout(_row, bgc=_header)
    _frame = mUI.MelFrameLayout(
        _sub_column,
        label=grp['label'],
        vis=True,
        collapse=False,
        collapsable=True,
        enable=True,
        marginWidth=5,
        marginHeight=2,
        bgc=_header,
    )
    _inside = mUI.MelColumnLayout(_frame, bgc=_header, adj=True, rowSpacing=0)

    _idx = start_idx
    for _entry in grp['entries']:
        self._l_opened_entries.append(_entry)
        _indices.append(_idx)
        uiFunc_build_opened_file_row(_inside, self, _entry, _idx, _file_cbs)
        _idx += 1

    mUI.MelButton(
        _row,
        l='R',
        w=22,
        bgc=cgmUI.guiButtonColor,
        ann='Revert changelist — checked files only, or all if none checked',
        c=cgmGEN.Callback(uiFunc_changelist_revert, self, _change_key),
    )
    mUI.MelButton(
        _row,
        l='S',
        w=22,
        bgc=cgmUI.guiButtonColor,
        ann='Submit changelist — checked files only, or all if none checked',
        c=cgmGEN.Callback(uiFunc_changelist_submit, self, _change_key),
    )
    mUI.MelButton(
        _row,
        l='Sh',
        w=22,
        bgc=cgmUI.guiButtonColor,
        ann='Shelve changelist — checked files only, or all if none checked',
        c=cgmGEN.Callback(uiFunc_changelist_shelve, self, _change_key),
    )
    mUI.MelSpacer(_row, w=5)

    _row.setStretchWidget(_sub_column)
    _row.layout()

    self._d_opened_cl_ui[_change_key] = {
        'change': grp['change'],
        'master_cb': _master_cb,
        'file_cbs': _file_cbs,
        'indices': _indices,
    }
    return _idx


def uiFunc_build_opened_rows(self, opened_dat):
    self.uiFrame_opened.clear()
    self._l_opened_entries = []
    self._d_opened_cl_ui = {}

    if not opened_dat:
        _uiFunc_set_section_empty_state(
            self, 'uiFrame_opened', 'uiRow_opened_empty', 'uiLabel_opened_empty', '(not loaded)')
        return

    if opened_dat.get('error'):
        _uiFunc_set_section_empty_state(
            self, 'uiFrame_opened', 'uiRow_opened_empty', 'uiLabel_opened_empty',
            opened_dat['error'])
        return

    _groups = P4UTIL.iter_opened_changelist_groups(opened_dat)
    if not _groups:
        _uiFunc_set_section_empty_state(
            self, 'uiFrame_opened', 'uiRow_opened_empty', 'uiLabel_opened_empty',
            '(no opened files)')
        return

    _uiFunc_set_section_content_state(self, 'uiFrame_opened', 'uiRow_opened_empty')

    _idx = 0
    for _grp in _groups:
        _idx = uiFunc_build_opened_changelist_section(self, self.uiFrame_opened, _grp, _idx)
        mUI.MelSeparator(self.uiFrame_opened, h=3)


def uiFunc_build_shelved_file_row(parent, self, entry, idx, file_cbs):
    _bgc = _ROW_BGC_EVEN if MATH.is_even(idx) else _ROW_BGC_ODD
    _row = mUI.MelHSingleStretchLayout(parent, h=30, bgc=_bgc, padding=2)
    mUI.MelSpacer(_row, w=5)

    _cb = mUI.MelCheckBox(_row, value=1)
    file_cbs.append(_cb)

    _action = entry.get('action', '?')
    _rev = entry.get('rev')
    _path = _shelf_entry_path(entry)
    _base = os.path.basename(_path)
    _rev_s = '#{0}'.format(_rev) if _rev is not None else ''
    _label = '{0} {1}{2}'.format(_base, _action, _rev_s)

    mUI.MelLabel(_row, l=_label, ann=_path)
    _row.setStretchWidget(mUI.MelLabel(_row, l=''))

    mUI.MelButton(
        _row, l='Delete', bgc=cgmUI.guiButtonColor,
        ann='p4 shelve -d {0}'.format(_path),
        c=cgmGEN.Callback(uiFunc_shelf_row_delete, self, idx),
    )
    mUI.MelSpacer(_row, w=5)
    _row.layout()
    mUI.MelSeparator(parent, h=1)


def uiFunc_build_shelved_changelist_section(self, parent, grp, start_idx):
    _change_key = _shelved_change_key(grp['change'])
    _header = _SHELVED_CL_HEADER_BGC
    _file_cbs = []
    _indices = []

    _row = mUI.MelHSingleStretchLayout(parent, bgc=_header, padding=2)
    _master_cb = mUI.MelCheckBox(
        _row,
        value=1,
        ann='Select all shelved files in this changelist for D / Mv / Sub',
        changeCommand=cgmGEN.Callback(uiFunc_toggle_shelf_cl_checks, self, _change_key),
    )
    mUI.MelSpacer(_row, w=5)

    _sub_column = mUI.MelColumnLayout(_row, bgc=_header)
    _frame = mUI.MelFrameLayout(
        _sub_column,
        label=grp['label'],
        vis=True,
        collapse=False,
        collapsable=True,
        enable=True,
        marginWidth=5,
        marginHeight=2,
        bgc=_header,
    )
    _inside = mUI.MelColumnLayout(_frame, bgc=_header, adj=True, rowSpacing=0)

    _idx = start_idx
    for _entry in grp['entries']:
        self._l_shelved_entries.append(_entry)
        _indices.append(_idx)
        uiFunc_build_shelved_file_row(_inside, self, _entry, _idx, _file_cbs)
        _idx += 1

    mUI.MelButton(
        _row,
        l='D',
        w=22,
        bgc=cgmUI.guiButtonColor,
        ann='Delete shelf — checked files only, or all shelved if none checked',
        c=cgmGEN.Callback(uiFunc_shelf_changelist_delete, self, _change_key),
    )
    mUI.MelButton(
        _row,
        l='Mv',
        w=26,
        bgc=cgmUI.guiButtonColor,
        ann='Move to changelist — unshelve checked files into target CL, then delete from source shelf',
        c=cgmGEN.Callback(uiFunc_shelf_changelist_move, self, _change_key),
    )
    mUI.MelButton(
        _row,
        l='Sub',
        w=28,
        bgc=cgmUI.guiButtonColor,
        ann='Submit shelved changelist (p4 submit -e)',
        c=cgmGEN.Callback(uiFunc_shelf_changelist_submit, self, _change_key),
    )
    mUI.MelSpacer(_row, w=5)

    _row.setStretchWidget(_sub_column)
    _row.layout()

    self._d_shelved_cl_ui[_change_key] = {
        'change': grp['change'],
        'master_cb': _master_cb,
        'file_cbs': _file_cbs,
        'indices': _indices,
    }
    return _idx


def uiFunc_build_shelved_rows(self, shelved_dat):
    self.uiFrame_shelved.clear()
    self._l_shelved_entries = []
    self._d_shelved_cl_ui = {}

    if not shelved_dat:
        _uiFunc_set_section_empty_state(
            self, 'uiFrame_shelved', 'uiRow_shelved_empty', 'uiLabel_shelved_empty', '(not loaded)')
        return

    if shelved_dat.get('error'):
        _uiFunc_set_section_empty_state(
            self, 'uiFrame_shelved', 'uiRow_shelved_empty', 'uiLabel_shelved_empty',
            shelved_dat['error'])
        return

    _groups = P4UTIL.iter_shelved_changelist_groups(shelved_dat)
    if not _groups:
        _uiFunc_set_section_empty_state(
            self, 'uiFrame_shelved', 'uiRow_shelved_empty', 'uiLabel_shelved_empty',
            '(no shelved changelists)')
        return

    _uiFunc_set_section_content_state(self, 'uiFrame_shelved', 'uiRow_shelved_empty')

    _idx = 0
    for _grp in _groups:
        _idx = uiFunc_build_shelved_changelist_section(self, self.uiFrame_shelved, _grp, _idx)
        mUI.MelSeparator(self.uiFrame_shelved, h=3)


def uiFunc_changelist_revert(self, change_key):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return

    _ui, _selected_entries = uiFunc_get_cl_selection(self, change_key)
    if not _ui:
        return

    _change = _ui['change']
    _total = len(_ui['indices'])
    _selected_paths = [_opened_entry_label_path(_e) for _e in _selected_entries]

    if _selected_entries and len(_selected_entries) < _total:
        _msg = (
            'Revert {0} selected file(s) in changelist {1}?\n\n{2}'.format(
                len(_selected_entries), _change, _format_cl_entry_preview(_selected_entries))
        )
    elif _selected_entries:
        _msg = 'Revert all {0} file(s) in changelist {1}?\n\n{2}'.format(
            len(_selected_entries), _change, _format_cl_entry_preview(_selected_entries))
    else:
        _msg = (
            'No files checked in changelist {0}.\n\n'
            'Revert ALL {1} opened file(s) in this changelist?'.format(_change, _total)
        )

    _result = mc.confirmDialog(
        title='Revert changelist',
        message=_msg,
        button=['Revert', 'Cancel'],
        defaultButton='Cancel',
        cancelButton='Cancel',
        dismissString='Cancel',
    )
    if _result != 'Revert':
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)

    if _selected_entries and len(_selected_entries) < _total:
        _failures = []
        for _entry in _selected_entries:
            _path = _opened_entry_label_path(_entry)
            _res = P4UTIL.revert_opened_entry(_entry, p4_user=_user, p4_client=_client)
            if _res.get('ok'):
                log.info('Reverted: {0}'.format(_path))
            else:
                _failures.append('{0}: {1}'.format(_path, _res.get('stderr') or 'unknown'))
        if _failures:
            log.error('Some reverts failed:\n{0}'.format('\n'.join(_failures)))
    else:
        _res = P4UTIL.revert_change(_change, p4_user=_user, p4_client=_client)
        if _res.get('ok'):
            log.info('Reverted changelist: {0}'.format(_change))
        else:
            log.error('Revert changelist failed: {0}'.format(_res.get('stderr') or 'unknown'))

    uiFunc_refresh(self, force=True)


def uiFunc_changelist_submit(self, change_key):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return

    _ui, _selected_entries = uiFunc_get_cl_selection(self, change_key)
    if not _ui:
        return

    _change = _ui['change']
    _total = len(_ui['indices'])

    if _selected_entries and len(_selected_entries) < _total:
        _msg = (
            'Submit {0} selected file(s) in changelist {1}?\n\n{2}'.format(
                len(_selected_entries), _change, _format_cl_entry_preview(_selected_entries))
        )
    elif _selected_entries:
        _msg = 'Submit all {0} file(s) in changelist {1}?\n\n{2}'.format(
            len(_selected_entries), _change, _format_cl_entry_preview(_selected_entries))
    else:
        _msg = (
            'No files checked in changelist {0}.\n\n'
            'Submit ALL {1} opened file(s) in this changelist?'.format(_change, _total)
        )

    if str(_change).lower() == 'default' and (not _selected_entries or len(_selected_entries) == _total):
        _count = len(_selected_entries) if _selected_entries else _total
        _msg = (
            'Submit default changelist?\n\n'
            'This submits ALL files in the default changelist ({0} file(s)).'.format(_count)
        )

    _result = mc.confirmDialog(
        title='Submit changelist',
        message=_msg,
        button=['Submit', 'Cancel'],
        defaultButton='Cancel',
        cancelButton='Cancel',
        dismissString='Cancel',
    )
    if _result != 'Submit':
        return

    _desc_msg = _msg
    _desc = uiFunc_prompt_change_description(
        'Submit to Perforce', _desc_msg, _change, _user, _client)
    if not _desc:
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)

    if _selected_entries and len(_selected_entries) < _total:
        _res = uiFunc_run_submit_paths(
            _change, _desc, _selected_entries, _user, _client)
        uiFunc_log_submit_result(
            _res,
            'Submitted {0} file(s) from changelist {1}'.format(
                len(_selected_entries), _change),
            fail_prefix='Submit selected failed',
        )
    else:
        _submit_count = len(_selected_entries) if _selected_entries else _total
        _res = uiFunc_run_submit_change(
            _change, _desc, _user, _client, file_count=_submit_count)
        uiFunc_log_submit_result(
            _res,
            'Submitted changelist: {0}'.format(_change),
            fail_prefix='Submit changelist failed',
        )

    uiFunc_refresh(self, force=True)


def uiFunc_changelist_shelve(self, change_key):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return

    _ui, _selected_entries = uiFunc_get_cl_selection(self, change_key)
    if not _ui:
        return

    _change = _ui['change']
    _total = len(_ui['indices'])

    if _selected_entries and len(_selected_entries) < _total:
        _msg = (
            'Shelve {0} selected file(s) in changelist {1}?\n\n{2}'.format(
                len(_selected_entries), _change, _format_cl_entry_preview(_selected_entries))
        )
    elif _selected_entries:
        _msg = 'Shelve all {0} file(s) in changelist {1}?\n\n{2}'.format(
            len(_selected_entries), _change, _format_cl_entry_preview(_selected_entries))
    else:
        _msg = (
            'No files checked in changelist {0}.\n\n'
            'Shelve ALL {1} opened file(s) in this changelist?'.format(_change, _total)
        )

    _result = mc.confirmDialog(
        title='Shelve changelist',
        message=_msg,
        button=['Shelve', 'Cancel'],
        defaultButton='Cancel',
        cancelButton='Cancel',
        dismissString='Cancel',
    )
    if _result != 'Shelve':
        return

    _desc = uiFunc_prompt_change_description(
        'Shelve to Perforce', _msg, _change, _user, _client)
    if not _desc:
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)

    if _selected_entries and len(_selected_entries) < _total:
        _res = P4UTIL.shelve_paths(
            None, change=_change, description=_desc,
            opened_entries=_selected_entries,
            p4_user=_user, p4_client=_client)
        if _res.get('ok'):
            log.info('Shelved {0} file(s) from changelist {1}'.format(
                len(_selected_entries), _change))
        else:
            log.error('Shelve selected failed: {0}'.format(_res.get('stderr') or 'unknown'))
    else:
        _res = P4UTIL.shelve_change(
            _change, description=_desc, p4_user=_user, p4_client=_client)
        if _res.get('ok'):
            log.info('Shelved changelist: {0}'.format(_change))
        else:
            log.error('Shelve changelist failed: {0}'.format(_res.get('stderr') or 'unknown'))

    uiFunc_refresh(self, force=True)


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


def uiFunc_refresh(self, force=False):
    _user, _client = uiFunc_get_connection(self)
    if force:
        P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)

    _dat = P4UTIL.query_connection(p4_user=_user, p4_client=_client, force=force)
    self._p4_status_dat = _dat

    _conn = _dat.get('connection') or {}

    if not _user or not _client:
        self._p4_status_dat = None
        uiFunc_set_status_panel(self, ['Set User and Client, then Refresh.'])
        uiFunc_build_opened_rows(self, None)
        uiFunc_build_shelved_rows(self, None)
        return

    if not _dat.get('connected'):
        uiFunc_set_status_panel(self, [
            'Not connected',
            _dat.get('reason') or _conn.get('reason') or 'unknown',
        ])
        uiFunc_build_opened_rows(self, None)
        uiFunc_build_shelved_rows(self, None)
        return

    _root = _conn.get('clientRoot') or '(not reported)'
    _stream = _conn.get('clientStream') or _conn.get('stream') or '(none)'
    uiFunc_set_status_panel(self, [
        'Connected as {0} @ {1}'.format(_conn.get('userName') or _user, _conn.get('clientName') or _client),
        'Root: {0}'.format(_root),
        'Stream: {0}'.format(_stream),
    ])

    uiFunc_build_opened_rows(self, _dat.get('opened'))
    uiFunc_build_shelved_rows(self, _dat.get('shelved'))

    if force:
        _path = (self.tf_query_path.getValue() or '').strip()
        if _path:
            _path_dat = P4UTIL.query_path(_path, p4_user=_user, p4_client=_client, force=True)
            self.uiLabel_path(edit=True, l=P4UTIL.format_file_status(_path_dat))


def uiFunc_sync_workspace(self):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        log.warning('Set User and Client first.')
        return

    _result = mc.confirmDialog(
        title='Sync Workspace',
        message='Sync entire client workspace to head?\n\nThis updates all mapped files for client:\n{0}'.format(
            _client),
        button=['Sync', 'Cancel'],
        defaultButton='Sync',
        cancelButton='Cancel',
        dismissString='Cancel',
    )
    if _result != 'Sync':
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    _res = P4UTIL.sync_workspace(p4_user=_user, p4_client=_client)
    if _res.get('ok'):
        log.info('Sync workspace complete: {0}'.format(_res.get('target')))
    else:
        log.error('Sync workspace failed: {0}'.format(_res.get('stderr') or 'unknown'))
    uiFunc_refresh(self, force=True)


def uiFunc_row_revert(self, idx):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return

    try:
        _entry = self._l_opened_entries[idx]
    except (IndexError, TypeError):
        return

    _path = _opened_entry_label_path(_entry)

    _result = mc.confirmDialog(
        title='Revert file',
        message='Revert opened file?\n\n{0}'.format(_path),
        button=['Revert', 'Cancel'],
        defaultButton='Cancel',
        cancelButton='Cancel',
        dismissString='Cancel',
    )
    if _result != 'Revert':
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    _res = P4UTIL.revert_opened_entry(_entry, p4_user=_user, p4_client=_client)
    if _res.get('ok'):
        log.info('Reverted: {0}'.format(_path))
    else:
        log.error('Revert failed: {0}'.format(_res.get('stderr') or 'unknown'))
    uiFunc_refresh(self, force=True)


def uiFunc_row_submit(self, idx):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return

    try:
        _entry = self._l_opened_entries[idx]
    except (IndexError, TypeError):
        return

    _change = _entry.get('change', 'default')
    _path = _entry.get('depotFile') or _entry.get('clientFile')
    if not _path:
        return

    _change_key = str(_change).lower()
    _count = sum(
        1 for _e in self._l_opened_entries
        if str(_e.get('change', 'default')).lower() == _change_key
    )
    _msg = 'Submit this file only:\n\n{0}'.format(os.path.basename(_path))
    if _count > 1:
        _msg = (
            'Submit this file only.\n\n{0} other opened file(s) in changelist {1} '
            'will remain pending.\n\n{2}'.format(_count - 1, _change, os.path.basename(_path))
        )

    _desc = uiFunc_prompt_change_description(
        'Submit to Perforce', _msg, _change, _user, _client)
    if not _desc:
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    _res = uiFunc_run_submit_paths(_change, _desc, [_entry], _user, _client)
    uiFunc_log_submit_result(_res, 'Submitted: {0}'.format(_path))
    uiFunc_refresh(self, force=True)


def uiFunc_row_shelve(self, idx):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return

    try:
        _entry = self._l_opened_entries[idx]
    except (IndexError, TypeError):
        return

    _change = _entry.get('change', 'default')
    _path = _entry.get('depotFile') or _entry.get('clientFile')
    if not _path:
        return

    _change_key = str(_change).lower()
    _count = sum(
        1 for _e in self._l_opened_entries
        if str(_e.get('change', 'default')).lower() == _change_key
    )
    _msg = 'Shelve this file only:\n\n{0}'.format(os.path.basename(_path))
    if _count > 1:
        _msg = (
            'Shelve this file only.\n\n{0} other opened file(s) in changelist {1} '
            'will remain pending.\n\n{2}'.format(_count - 1, _change, os.path.basename(_path))
        )

    _desc = uiFunc_prompt_change_description(
        'Shelve to Perforce', _msg, _change, _user, _client)
    if not _desc:
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    _res = P4UTIL.shelve_paths(
        None, change=_change, description=_desc,
        opened_entries=[_entry],
        p4_user=_user, p4_client=_client)
    if _res.get('ok'):
        log.info('Shelved: {0}'.format(_path))
    else:
        log.error('Shelve failed: {0}'.format(_res.get('stderr') or 'unknown'))
    uiFunc_refresh(self, force=True)


def uiFunc_shelf_get_action_paths(self, change_key):
    """Return (ui_dict, paths, mode) for shelved CL actions. mode is partial or all."""
    _ui, _selected_paths = uiFunc_get_shelf_cl_selection(self, change_key)
    if not _ui:
        return None, None, None
    _total = len(_ui['indices'])
    if not _selected_paths:
        _all_paths = []
        for _idx in _ui['indices']:
            try:
                _path = _shelf_entry_path(self._l_shelved_entries[_idx])
            except IndexError:
                continue
            if _path and _path != '?':
                _all_paths.append(_path)
        return _ui, _all_paths, 'all'
    if len(_selected_paths) < _total:
        return _ui, _selected_paths, 'partial'
    return _ui, _selected_paths, 'all'


def uiFunc_prompt_shelf_target_changelist(self, source_change, user, client):
    """Prompt for target changelist number, default, or new."""
    _pending = []
    _dat = getattr(self, '_p4_status_dat', None) or {}
    _pending_dat = _dat.get('pendingChanges') or {}
    for _ch in _pending_dat.get('changes') or []:
        _cl = _ch.get('change')
        if _cl is not None and str(_cl) != str(source_change):
            _pending.append(str(_cl))
    _msg = 'Enter target changelist: number, default, or new'
    if _pending:
        _msg += '\n\nPending changelists: {0}'.format(', '.join(_pending[:24]))
    _raw = cgmUI.uiPrompt_getValue(
        title='Move to changelist',
        message=_msg,
        style='text',
    )
    if _raw is None:
        return None
    _raw = _raw.strip()
    if not _raw:
        log.warning('Move to changelist: target required')
        return None
    _lower = _raw.lower()
    if _lower in ('default', 'new'):
        return _lower
    try:
        _target = int(_raw)
    except (TypeError, ValueError):
        log.error('Move to changelist: invalid target "{0}"'.format(_raw))
        return None
    if str(_target) == str(source_change):
        log.error('Move to changelist: target cannot be the same as source ({0})'.format(_target))
        return None
    return _target


def uiFunc_shelf_changelist_move(self, change_key):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return

    _ui, _paths, _mode = uiFunc_shelf_get_action_paths(self, change_key)
    if not _ui or not _paths:
        return log.warning('Move to changelist: no shelved files selected')

    _change = _ui['change']
    _total = len(_ui['indices'])

    if _mode == 'partial':
        _msg = (
            'Move {0} selected shelved file(s) from changelist {1} to another changelist?\n\n'
            'Files will be unshelved (opened) on the target CL and removed from this shelf.\n\n{2}'.format(
                len(_paths), _change, _format_cl_path_preview(_paths))
        )
    else:
        _msg = (
            'Move all {0} shelved file(s) from changelist {1} to another changelist?\n\n'
            'Files will be unshelved (opened) on the target CL and removed from this shelf.\n\n{2}'.format(
                len(_paths), _change, _format_cl_path_preview(_paths))
        )

    _result = mc.confirmDialog(
        title='Move to changelist',
        message=_msg,
        button=['Move', 'Cancel'],
        defaultButton='Cancel',
        cancelButton='Cancel',
        dismissString='Cancel',
    )
    if _result != 'Move':
        return

    _target = uiFunc_prompt_shelf_target_changelist(self, _change, _user, _client)
    if _target is None:
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)

    if _target == 'new':
        _desc = cgmUI.uiPrompt_getValue(
            title='New changelist',
            message='Description for the new target changelist:',
            style='text',
        )
        if _desc is None:
            return
        _desc = _desc.strip()
        if not _desc:
            log.warning('Move to changelist: description required for new changelist')
            return
        _create = P4UTIL.create_pending_change(
            _desc, p4_user=_user, p4_client=_client)
        if not _create.get('ok'):
            log.error('Move to changelist: create changelist failed: {0}'.format(
                _create.get('stderr') or 'unknown'))
            return
        _target = _create.get('change')
        log.info('Created changelist {0} for move target'.format(_target))

    if _mode == 'partial':
        _res = P4UTIL.move_shelf_paths(
            _paths, source_change=_change, target_change=_target,
            p4_user=_user, p4_client=_client)
    else:
        if len(_paths) < _total:
            _res = P4UTIL.move_shelf_paths(
                _paths, source_change=_change, target_change=_target,
                p4_user=_user, p4_client=_client)
        else:
            _res = P4UTIL.move_shelf_change(
                _change, target_change=_target, p4_user=_user, p4_client=_client)

    if _res.get('ok'):
        log.info('Moved {0} shelved file(s) from changelist {1} to {2}'.format(
            len(_paths), _change, _target))
    else:
        log.error('Move to changelist failed: {0}'.format(_res.get('stderr') or 'unknown'))
        if _res.get('unshelved'):
            log.warning(
                'Files were unshelved to {0} but source shelf delete failed — review in P4V'.format(
                    _target))
    uiFunc_refresh(self, force=True)


def uiFunc_shelf_changelist_delete(self, change_key):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return

    _ui, _selected_paths = uiFunc_get_shelf_cl_selection(self, change_key)
    if not _ui:
        return

    _change = _ui['change']
    _total = len(_ui['indices'])

    if _selected_paths and len(_selected_paths) < _total:
        _msg = (
            'Delete shelf for {0} selected file(s) in changelist {1}?\n\n{2}'.format(
                len(_selected_paths), _change, _format_cl_path_preview(_selected_paths))
        )
    elif _selected_paths:
        _msg = 'Delete entire shelf ({0} file(s)) in changelist {1}?\n\n{2}'.format(
            len(_selected_paths), _change, _format_cl_path_preview(_selected_paths))
    else:
        _msg = (
            'No files checked in changelist {0}.\n\n'
            'Delete ALL {1} shelved file(s) in this changelist?'.format(_change, _total)
        )

    _result = mc.confirmDialog(
        title='Delete shelf',
        message=_msg,
        button=['Delete', 'Cancel'],
        defaultButton='Cancel',
        cancelButton='Cancel',
        dismissString='Cancel',
    )
    if _result != 'Delete':
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)

    if _selected_paths and len(_selected_paths) < _total:
        _res = P4UTIL.delete_shelf_paths(
            _selected_paths, change=_change, p4_user=_user, p4_client=_client)
        if _res.get('ok'):
            log.info('Deleted shelf for {0} file(s) in changelist {1}'.format(
                len(_selected_paths), _change))
        else:
            log.error('Delete shelf failed: {0}'.format(_res.get('stderr') or 'unknown'))
    else:
        _res = P4UTIL.delete_shelf_change(_change, p4_user=_user, p4_client=_client)
        if _res.get('ok'):
            log.info('Deleted shelf for changelist: {0}'.format(_change))
        else:
            log.error('Delete shelf failed: {0}'.format(_res.get('stderr') or 'unknown'))

    uiFunc_refresh(self, force=True)


def uiFunc_shelf_changelist_submit(self, change_key):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return

    _ui, _selected_paths = uiFunc_get_shelf_cl_selection(self, change_key)
    if not _ui:
        return

    _change = _ui['change']
    _total = len(_ui['indices'])

    if _selected_paths and len(_selected_paths) < _total:
        log.warning('Submit shelved: partial file submit not supported — submit whole changelist {0}'.format(
            _change))
        return

    _msg = 'Submit shelved changelist {0} ({1} file(s)) to depot?'.format(_change, _total)
    _result = mc.confirmDialog(
        title='Submit shelved',
        message=_msg,
        button=['Submit', 'Cancel'],
        defaultButton='Cancel',
        cancelButton='Cancel',
        dismissString='Cancel',
    )
    if _result != 'Submit':
        return

    _desc = uiFunc_prompt_change_description(
        'Submit Shelved to Perforce', _msg, _change, _user, _client)
    if not _desc:
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    _res = P4UTIL.submit_shelved_change(
        _change, description=_desc, p4_user=_user, p4_client=_client)
    if _res.get('ok'):
        log.info('Submitted shelved changelist: {0}'.format(_change))
    else:
        log.error('Submit shelved failed: {0}'.format(_res.get('stderr') or 'unknown'))
    uiFunc_refresh(self, force=True)


def uiFunc_shelf_row_delete(self, idx):
    _user, _client = uiFunc_get_connection(self)
    if not _user or not _client:
        return

    try:
        _entry = self._l_shelved_entries[idx]
    except (IndexError, TypeError):
        return

    _change = _entry.get('change')
    _path = _shelf_entry_path(_entry)
    if not _path or _path == '?':
        return

    _result = mc.confirmDialog(
        title='Delete from shelf',
        message='Delete shelved file from changelist {0}?\n\n{1}'.format(
            _change, os.path.basename(_path)),
        button=['Delete', 'Cancel'],
        defaultButton='Cancel',
        cancelButton='Cancel',
        dismissString='Cancel',
    )
    if _result != 'Delete':
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    _res = P4UTIL.delete_shelf_paths(
        [_path], change=_change, p4_user=_user, p4_client=_client)
    if _res.get('ok'):
        log.info('Deleted from shelf: {0}'.format(_path))
    else:
        log.error('Delete from shelf failed: {0}'.format(_res.get('stderr') or 'unknown'))
    uiFunc_refresh(self, force=True)


def uiFunc_use_scene_path(self):
    _scene = mc.file(q=True, sn=True)
    if _scene:
        self.tf_query_path(edit=True, text=_scene)
    else:
        log.warning('Scene is not saved — no path to use')


def uiFunc_query_path(self):
    _user, _client = uiFunc_get_connection(self)
    _path = (self.tf_query_path.getValue() or '').strip()

    if not _path:
        self.uiLabel_path(edit=True, l='Enter a path to query.')
        return
    if not _user or not _client:
        self.uiLabel_path(edit=True, l='Set User and Client first.')
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    _dat = P4UTIL.query_path_report(_path, p4_user=_user, p4_client=_client, force=True)
    self.uiLabel_path(edit=True, l=P4UTIL.format_file_status(_dat))


def uiFunc_checkout_path(self):
    _user, _client = uiFunc_get_connection(self)
    _path = (self.tf_query_path.getValue() or '').strip()

    if not _path:
        self.uiLabel_path(edit=True, l='Enter a path to checkout.')
        return
    if not _user or not _client:
        self.uiLabel_path(edit=True, l='Set User and Client first.')
        return

    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    _res = P4UTIL.edit_or_add(_path, p4_user=_user, p4_client=_client, force=True)
    if _res.get('ok'):
        log.info('Checkout ({0}): {1}'.format(_res.get('action'), _path))
    else:
        log.error('Checkout failed: {0}'.format(_res.get('stderr') or 'unknown'))
        self.uiLabel_path(edit=True, l='Checkout failed: {0}'.format(_res.get('stderr') or 'unknown'))
        return

    _dat = P4UTIL.query_path_report(_path, p4_user=_user, p4_client=_client, force=True)
    self.uiLabel_path(edit=True, l=P4UTIL.format_file_status(_dat))
    uiFunc_refresh(self, force=True)
