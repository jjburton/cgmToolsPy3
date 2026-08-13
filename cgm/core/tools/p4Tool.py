"""
------------------------------------------
p4Tool : cgm.core.tools
Simple Perforce connection UI — user/client prefs + status.
------------------------------------------
"""
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

import maya.cmds as mc

import cgm.core.classes.GuiFactory as cgmUI
import cgm.core.cgm_Meta as cgmMeta
import cgm.core.cgm_General as cgmGEN
import cgm.core.lib.perforce as P4UTIL

mUI = cgmUI.mUI

__version__ = cgmGEN.__RELEASESTRING
__toolname__ = 'cgmP4'
_padding = 5


class ui(cgmUI.cgmGUI):
    USE_Template = 'cgmUITemplate'
    WINDOW_NAME = '{0}_ui'.format(__toolname__)
    WINDOW_TITLE = '{1} - {0}'.format(__version__, __toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = True
    DEFAULT_SIZE = 460, 340
    TOOLNAME = '{0}.ui'.format(__toolname__)

    def insert_init(self, *args, **kws):
        self.var_p4_user = cgmMeta.cgmOptionVar(P4UTIL.OPT_P4_USER, varType='string', defaultValue='')
        self.var_p4_client = cgmMeta.cgmOptionVar(P4UTIL.OPT_P4_CLIENT, varType='string', defaultValue='')

    def build_menus(self):
        self.uiMenu_FirstMenu = mUI.MelMenu(l='Setup', pmc=cgmGEN.Callback(self.buildMenu_first))

    def buildMenu_first(self):
        self.uiMenu_FirstMenu.clear()
        mUI.MelMenuItem(
            self.uiMenu_FirstMenu,
            l='Reload',
            ann='Reload p4Tool and perforce lib',
            c=cgmGEN.Callback(self.reload),
        )

    def reload(self):
        cgmGEN._reloadMod(P4UTIL)
        cgmGEN._reloadMod(__import__(__name__))
        super(ui, self).reload()

    def build_layoutWrapper(self, parent):
        _main = mUI.MelFormLayout(self, ut='cgmUITemplate')
        _column = mUI.MelColumnLayout(_main, adj=True, rowSpacing=_padding)

        mUI.MelLabel(_column, l='Perforce user and client workspace (saved to optionVars).', ut='cgmUISubTemplate')

        _row_user = mUI.MelHSingleStretchLayout(_column, ut='cgmUISubTemplate')
        mUI.MelLabel(_row_user, l='User', w=50)
        self.tf_p4_user = mUI.MelTextField(_row_user, text=self.var_p4_user.getValue() or '', ann='P4USER')
        _row_user.setStretchWidget(self.tf_p4_user)
        _row_user.layout()

        _row_client = mUI.MelHSingleStretchLayout(_column, ut='cgmUISubTemplate')
        mUI.MelLabel(_row_client, l='Client', w=50)
        self.tf_p4_client = mUI.MelTextField(
            _row_client, text=self.var_p4_client.getValue() or '', ann='P4CLIENT workspace name')
        _row_client.setStretchWidget(self.tf_p4_client)
        _row_client.layout()

        _row_btns = mUI.MelHLayout(_column, ut='cgmUISubTemplate', padding=_padding)
        mUI.MelButton(
            _row_btns,
            l='Save',
            ut='cgmUITemplate',
            ann='Save user/client to cgm optionVars',
            c=cgmGEN.Callback(uiFunc_save, self),
        )
        mUI.MelButton(
            _row_btns,
            l='Refresh',
            ut='cgmUITemplate',
            ann='Query p4 info and update status (also logs to Script Editor)',
            c=cgmGEN.Callback(uiFunc_refresh, self),
        )
        _row_btns.layout()

        mUI.MelSeparator(_column, style='none', height=_padding)
        mUI.MelLabel(_column, l='Status', ut='cgmUISubTemplate')

        self.uiLabel_status = mUI.MelLabel(
            _column, l='(click Refresh)', ut='cgmUIInstructionsTemplate', align='left')
        self.uiLabel_clientRoot = mUI.MelLabel(_column, l='', ut='cgmUIInstructionsTemplate', align='left')
        self.uiLabel_stream = mUI.MelLabel(_column, l='', ut='cgmUIInstructionsTemplate', align='left')
        self.uiLabel_opened = mUI.MelLabel(_column, l='', ut='cgmUIInstructionsTemplate', align='left')
        self.uiLabel_scene = mUI.MelLabel(_column, l='', ut='cgmUIInstructionsTemplate', align='left')

        _row_footer = cgmUI.add_cgmFooter(_main)
        _main(edit=True,
               af=[(_column, 'top', 0),
                   (_column, 'left', 0),
                   (_column, 'right', 0),
                   (_row_footer, 'left', 0),
                   (_row_footer, 'right', 0),
                   (_row_footer, 'bottom', 0)],
               ac=[(_column, 'bottom', 2, _row_footer)],
               attachNone=[(_row_footer, 'top')])

    def post_init(self, *args, **kws):
        uiFunc_refresh(self, log_report=False)


def uiFunc_save(self):
    _user = (self.tf_p4_user.getValue() or '').strip()
    _client = (self.tf_p4_client.getValue() or '').strip()
    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)
    log.info('Saved P4 prefs: user={0} client={1}'.format(_user, _client))


def uiFunc_refresh(self, log_report=True):
    _user = (self.tf_p4_user.getValue() or '').strip()
    _client = (self.tf_p4_client.getValue() or '').strip()
    P4UTIL.save_connection_prefs(p4_user=_user, p4_client=_client)

    if log_report:
        _dat = P4UTIL.query_status_report(p4_user=_user, p4_client=_client, force=True)
    else:
        _dat = P4UTIL.query_connection(p4_user=_user, p4_client=_client, force=True)

    _conn = _dat.get('connection') or {}

    if not _user or not _client:
        self.uiLabel_status(edit=True, l='Set User and Client, then Refresh.')
        self.uiLabel_clientRoot(edit=True, l='')
        self.uiLabel_stream(edit=True, l='')
        self.uiLabel_opened(edit=True, l='')
        self.uiLabel_scene(edit=True, l='')
        return

    if not _dat.get('connected'):
        self.uiLabel_status(edit=True, l='Not connected: {0}'.format(_dat.get('reason') or 'unknown'))
        self.uiLabel_clientRoot(edit=True, l='')
        self.uiLabel_stream(edit=True, l='')
        self.uiLabel_opened(edit=True, l='')
        self.uiLabel_scene(edit=True, l='')
        return

    self.uiLabel_status(edit=True, l='Connected as {0} @ {1}'.format(
        _conn.get('userName') or _user, _conn.get('clientName') or _client))

    _root = _conn.get('clientRoot') or '(unknown)'
    self.uiLabel_clientRoot(edit=True, l='Root: {0}'.format(_root))

    _stream = _conn.get('clientStream') or _conn.get('stream') or '(none)'
    self.uiLabel_stream(edit=True, l='Stream: {0}'.format(_stream))

    _opened = _dat.get('opened') or {}
    if _opened.get('error'):
        self.uiLabel_opened(edit=True, l='Opened: {0}'.format(_opened['error']))
    else:
        self.uiLabel_opened(edit=True, l='Opened files: {0}'.format(_opened.get('total', 0)))

    _scene = _dat.get('scene') or {}
    if _scene.get('skipped'):
        self.uiLabel_scene(edit=True, l='Scene: {0}'.format(_scene.get('reason', 'n/a')))
    elif _scene.get('error'):
        self.uiLabel_scene(edit=True, l='Scene: {0}'.format(_scene['error']))
    else:
        _parts = []
        if _scene.get('onDepot'):
            _parts.append('onDepot')
        if _scene.get('haveRev') is not None:
            _parts.append('haveRev {0}'.format(_scene.get('haveRev')))
        if _scene.get('openAction'):
            _parts.append('open {0}'.format(_scene.get('openAction')))
        elif _scene.get('notInClient'):
            _parts.append('not in client')
        elif _scene.get('notOnDepot'):
            _parts.append('not on depot')
        self.uiLabel_scene(edit=True, l='Scene: {0}'.format(' | '.join(_parts) if _parts else '(ok)'))
