import maya.cmds as mc
#import pyunify.lib.node as node
import cgm.core.cgm_Meta as cgmMeta
import cgm.core.cgm_General as cgmGEN
import json
import os
import pprint
from functools import partial
import operator
import cgm.core.classes.GuiFactory as cgmUI
#reload(cgmUI)
mUI = cgmUI.mUI

#========================================================================
import logging
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
#========================================================================

class ShotUI(object):
    '''
Shot UI class.

Loads the Shot UI.

| outputs ShotUI

example:
.. python::

    import cgm.core.mrs.Shots as SHOTS
    x = SHOTS.ShotUI()
    '''
    def __init__(self):
        self.window                   = None

        self.cw    = 100
        self._colWidths = [(1, self.cw * 2.9), (2, self.cw*.25), (3, self.cw), (4, self.cw),
                           (5, self.cw*.25), (6, self.cw), (7, self.cw * .75), (8, self.cw * .1), (9, 25),
                           (10, self.cw * .1)]
        self.width = sum(w for _, w in self._colWidths)

        self.autoAdjustOptionVar = "shotUI_autoAdjustFrames"

        self.animDict           = {}
        self.animList           = []
        self.animUIDict         = {}
        self.animListNode       = None
        self.shotColumn         = None
        self.shotRCL            = None
        self.autoAdjustFramesMI = None

        self._defaultBGColor = [0,0,0]
        self._defaultButtonBGColor = [0,0,0]
        self._defaultSpacerBGColor = [0,0,0]

        self.sortType = 1

        self.LoadAnimList()

        self.CreateWindow()

    def CreateWindow(self):
        if(mc.window("pyunify_ShotsUI", exists=True)):
            mc.deleteUI("pyunify_ShotsUI", window=True)

        #    Create a window with a some fields for entering text.
        #
        # ut='cgmUITemplate' is what makes this window pick up GuiFactory's registered
        # mc.window(dt='cgmUITemplate', backgroundColor=guiBackgroundColor) deferred-template
        # entry (see initializeTemplates()) - without it the window falls back to Maya's
        # default (darker) window background instead of the house cgm gray. toolbox.py's own
        # windows (e.g. showAbout's mc.window(..., ut='cgmUITemplate', ...)) use the same kwarg.
        self.window = mc.window("pyunify_ShotsUI", title="Sub Animation List", menuBar=True, sizeable=True,
                                 ut='cgmUITemplate', widthHeight=(int(self.width), 400))

        mc.menu( label='Options' )
        self.autoAdjustFramesMI = mc.menuItem( label='Auto Adjust Frames', checkBox=True, command = self.SaveOptions )
        mc.menuItem( label='Find and Replace names', command = self.FindAndReplaceShotsUI )



        # adjustableColumn=True (instead of a fixed w=self.width) lets every full-width child
        # below stretch/shrink with the window instead of capping it at the old fixed total.
        self._mainColumn = mc.columnLayout(adjustableColumn=True)

        # Header row: mirrors the per-shot MelHSingleStretchLayout rows below it so the
        # "Name" column header tracks the stretchy nameField column as the window resizes.
        # h=25 matches the per-shot rows below (tallest sibling there is the 25px removeBtn
        # MelIconButton) so the formLayout's own bounds don't exceed its widgets' heights -
        # an oversized form otherwise leaves blank vertical space that reads as row spacing.
        # ut='cgmUIHeaderTemplate' only registers dt= entries for mc.text/separator/formLayout/
        # rowLayout/rowColumnLayout/columnLayout/textScrollList/frameLayout (GuiFactory.py
        # initializeTemplates) - there is no dt='cgmUIHeaderTemplate' registration for mc.button,
        # so tagging a MelButton with ut='cgmUIHeaderTemplate' alone silently keeps the regular
        # button look (same silent-no-effect failure mode as the MelIconButton pitfall above).
        # Pass bgc=cgmUI.guiHeaderColor explicitly on every header control - buttons, container,
        # and trailing spacers - so the whole row shows the header color with no gaps.
        headerRow = mUI.MelHSingleStretchLayout(self._mainColumn, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor, padding=0, h=25)

        headerNameBtn = mUI.MelButton(headerRow, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor, label="Name", command=partial(self.Sort, 0))
        mUI.MelButton(headerRow, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor, label="", w=int(self._colWidths[1][1]))
        mUI.MelButton(headerRow, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor, label="Start", w=int(self._colWidths[2][1]), command=partial(self.Sort, 1))
        mUI.MelButton(headerRow, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor, label="End", w=int(self._colWidths[3][1]), command=partial(self.Sort, 2))
        mUI.MelButton(headerRow, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor, label="", w=int(self._colWidths[4][1]))
        mUI.MelButton(headerRow, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor, label="Frames", w=int(self._colWidths[5][1]), command=partial(self.Sort, 3))

        # Trailing placeholders matching the shot rows' frameBtn / spacer / removeBtn / spacer
        # columns (colWidths[6], [7], the fixed 25px removeBtn, and colWidths[9] - see the
        # per-shot row below). Without these the header row's fixed-width total is smaller
        # than each shot row's, so with both rows using the SAME stretch-widget mechanism
        # (MelHSingleStretchLayout absorbing parent width minus fixed siblings), the header's
        # stretch widget (headerNameBtn) ends up wider than each row's nameField by exactly
        # that missing width - shifting every column after Name to the right relative to the
        # matching column in the shot rows below. Matching the fixed-width total here (rather
        # than only matching each column's own width) is what keeps Start/End/Frames aligned
        # with minField/maxField/lengthField.
        # MelSpacer.__new__ only takes (parent, w, h) - no bgc passthrough - so use MelLabel
        # (MelSpacer's own base class, same WIDGET_CMD = mc.text) with an explicit empty label
        # to keep these placeholders tinted the header color instead of plain gray gaps.
        mUI.MelLabel(headerRow, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor, l='', w=int(self._colWidths[6][1]), h=1)
        mUI.MelLabel(headerRow, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor, l='', w=int(self._colWidths[7][1]), h=1)
        mUI.MelLabel(headerRow, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor, l='', w=25, h=1)
        mUI.MelLabel(headerRow, ut='cgmUIHeaderTemplate', bgc=cgmUI.guiHeaderColor, l='', w=int(self._colWidths[9][1]), h=1)

        headerRow.setStretchWidget(headerNameBtn)
        headerRow.layout()

        mc.setParent('..')

        # Vertical container stacking one MelHSingleStretchLayout row per shot. adj=True so
        # each row stretches to the full (resizable) window width.
        self.shotRCL = mUI.MelColumnLayout(self._mainColumn, ut='cgmUITemplate', adj=True, rowSpacing=0)

        self.animUIDict = {}

        mc.setParent('..')

        mUI.MelSpacer(self._mainColumn, h=5)

        # No explicit w= here: the parent column's adjustableColumn=True stretches this row
        # to the window width too, so it stays visually consistent with the rows above it.
        _row_base = mUI.MelHLayout(self._mainColumn, ut='cgmUITemplate', padding=5)
        mUI.MelButton(_row_base, ut='cgmUITemplate', label="Add Sub Animation", command=self.AddShotUI)
        mUI.MelButton(_row_base, ut='cgmUITemplate', label="Refresh", command=self.RefreshShotListUI)

        _row_base.layout()

        # Inert, genuinely focusable "focus trap" control used by _ReleaseFieldFocus to pull
        # Qt keyboard focus off the shot name text fields. This window is a separate top-level
        # Qt window from Maya's main window/modelPanels, so mc.setFocus(<modelPanel>) only
        # changes Maya's internal "current panel" designation - it does not reliably move Qt's
        # actual keyboard focus out of a line-edit living in THIS window. Moving focus to a
        # real control inside this same top-level window is what actually blurs the field.
        # 1x1 px and non-editable so it never attracts attention or accepts typed input, but
        # a non-editable MelTextField can still be a mc.setFocus() target in Maya/Qt.
        # Parented directly to self._mainColumn (a plain columnLayout, not the weighted
        # MelHLayout above) so it doesn't take a 3rd equal share of _row_base's width.
        self._focusTrap = mUI.MelTextField(self._mainColumn, ut='cgmUITemplate', editable=False, w=1, h=1)

        mc.showWindow( self.window )

        self.Sort(self.sortType)

        if mc.optionVar( exists=self.autoAdjustOptionVar ):
            mc.menuItem( self.autoAdjustFramesMI, e=True, checkBox=mc.optionVar( q=self.autoAdjustOptionVar ))

    def SaveOptions(self, *args):
        mc.optionVar( iv=(self.autoAdjustOptionVar, mc.menuItem(self.autoAdjustFramesMI, q=True, checkBox=True) ) )

    def Sort(self, *args):
        self.sortType = args[0]

        if self.sortType == 0:
            self.animList = sorted(list(self.animDict.items()), key=operator.itemgetter(0))
        elif self.sortType == 1:
            self.animList = sorted(list(self.animDict.items()), key=lambda x: x[1][0])
        elif self.sortType == 2:
            self.animList = sorted(list(self.animDict.items()), key=lambda x: x[1][1]) 
        elif self.sortType == 3:
            self.animList = sorted(list(self.animDict.items()), key=lambda x: x[1][2])

        self.RefreshShotList()     

    def SetShotRange(self, *args, **kwargs):
        setMin = True
        setMax = True
        if 'min' in kwargs:
            setMin = kwargs['min']
        if 'max' in kwargs:
            setMax = kwargs['max']

        if setMin:
            mc.playbackOptions(e=True, min=self.animDict[args[0]][0])
        if setMax:
            mc.playbackOptions(e=True, max=self.animDict[args[0]][1])

        self.UpdateShotList()
        self._ReleaseFieldFocus()

    def _ReleaseFieldFocus(self):
        '''
        Move keyboard focus off the shot name text fields so typing does not
        edit a shot name.

        This window (self.window) is its own separate floating top-level Qt
        window - it is NOT docked inside Maya's main window where modelPanels
        live. mc.setFocus(<modelPanel>) only changes Maya's internal "current
        panel" designation (relevant to hotkeys/tool context); it is a
        different mechanism from Qt's actual keyboard/widget focus, and does
        not reliably steal Qt focus away from a field in a different
        top-level window. The reliable fix is to move focus to a real,
        focusable control inside THIS SAME top-level window - self._focusTrap,
        a 1x1 non-editable MelTextField created in CreateWindow for exactly
        this purpose.

        Deferred: issuing setFocus synchronously inside a button's command
        callback gets overridden once Maya restores focus to the clicked
        control after the callback returns, so the actual focus change has
        to happen after Maya's own post-click focus handling settles.
        '''
        def _doRelease():
            _trap = getattr(self, '_focusTrap', None)
            if _trap:
                try:
                    mc.setFocus(_trap)
                    return
                except Exception as e:
                    log.debug("Could not set focus to focus trap {}: {}".format(_trap, e))

            # Defensive fallback only - shouldn't normally trigger since _focusTrap is
            # created unconditionally in CreateWindow.
            _panel = mc.getPanel(withFocus=True)
            if not _panel or mc.getPanel(typeOf=_panel) != 'modelPanel':
                _modelPanels = mc.getPanel(type='modelPanel') or []
                _panel = _modelPanels[0] if _modelPanels else None

            if _panel:
                try:
                    mc.setFocus(_panel)
                except Exception as e:
                    log.debug("Could not set focus to {}: {}".format(_panel, e))

        mc.evalDeferred(_doRelease)

    def RemoveShot(self, *args):
        result = mc.confirmDialog(
                title='Remove Shot',
                message='Are you sure you want to remove shot: {0}'.format(args[0]),
                button=['OK', 'Cancel'],
                defaultButton='OK',
                cancelButton='Cancel',
                dismissString='Cancel')
        if result != 'OK':
            return

        self.animDict.pop(args[0], None)
        self.animListNode.subAnimList = self.animDict#json.dumps(self.animDict)

        self.Sort(self.sortType)
        
    def FindAndReplaceShotsUI(self, *args):
        if not self.animList:
            return log.warning("No animlist to search")
        
        window = mc.window(title="Find/Replace in Shots", iconName='Find/Replace in Shots') #cgmUI.cgmGUI()
        frColumn = mc.columnLayout()
        mc.rowColumnLayout( numberOfColumns=2, columnWidth=[(1, 80), (2, 200)], h=60  )
        mc.text( label='Find')

        find = mc.textField()

        mc.text( label='Replace')
        replace = mc.textField()

        mc.setParent('..')
        #mc.rowColumnLayout( numberOfColumns=2, columnWidth=[(1, 140), (2, 140)]  )
        mUI.MelButton(frColumn, ut='cgmUITemplate', label="OK", w=140, h=30, command=partial(self.FindAndReplaceFromUI, window, find, replace))
        #mc.button(label="Cancel", h=30, command=partial(mc.windoC, window) )
        mc.setParent('..')
        mc.setParent('..')

        mc.showWindow( window )        
        
    def FindAndReplaceFromUI(self, *args):
        str_func = 'FindAndReplaceFromUI'
        find = mc.textField(args[1], q=True, text=True)
        replace = mc.textField(args[2], q=True, text=True)
        mc.deleteUI(args[0], window=True)
        
        log.info(cgmGEN.logString_msg(str_func,"find: {}".format(find)))
        log.info(cgmGEN.logString_msg(str_func,"replace: {}".format(replace)))
        
        
        _dTmp = self.animDict
        _done = False
        for k,l in list(_dTmp.items()):
            if find in k:
                _new = k.replace(find,replace)
                log.info("Replacing: {} | {}".format(k,_new))
                _dTmp.pop(k)
                _dTmp[_new] = l
                _done = True
                
        if _done:
            self.animDict = _dTmp
            self.animListNode.subAnimList = self.animDict#json.dumps(self.animDict)        
        
        self.RefreshUI()
        #self.AddShot(name, minVal, maxVal)
        

    def AddShotUI(self, *args):
        window = mc.window(title="Add Shot", iconName='Add Shot')
        mc.columnLayout()
        mc.rowColumnLayout( numberOfColumns=2, columnWidth=[(1, 80), (2, 200)], h=60  )
        mc.text( label='Shot Name')
        import cgm.core.cgmPy.path_Utils as PATHS
        
        #pprint.pprint(self.animList)
        
        
        
        if self.animList:
            _text = self.animList[-1][0]
            
            minVal =  self.animList[-1][1][1]
            maxVal =  self.animList[-1][1][1] + self.animList[-1][1][2]          
            
        else:
            try:
                _text = PATHS.Path(mc.file(q=True, sn=True)).name()
            except:
                _text = ''
                
            minVal = mc.playbackOptions(q=True, min=True)
            maxVal = mc.playbackOptions(q=True, max=True)                
        
        name = mc.textField(text = _text)

        mc.text( label='Range' )
        shotRange = mc.intFieldGrp(numberOfFields=2, columnWidth=[(1, 96), (2, 99)])
        mc.setParent('..')
        okCancelRCL = mc.rowColumnLayout( numberOfColumns=2, columnWidth=[(1, 140), (2, 140)]  )
        mUI.MelButton(okCancelRCL, ut='cgmUITemplate', label="OK", w=140, h=30, command=partial(self.AddShotFromUI, window, name, shotRange))
        mUI.MelButton(okCancelRCL, ut='cgmUITemplate', label="Cancel", h=30, command=partial(self.DeleteAddShotUI, window) )
        mc.setParent('..')
        mc.setParent('..')



        mc.intFieldGrp(shotRange, e=True, v1=minVal, v2=maxVal)

        mc.showWindow( window )

    def DeleteAddShotUI(self, *args):
        mc.deleteUI(args[0], window=True)

    def AddShotFromUI(self, *args):
        name = mc.textField(args[1], q=True, text=True)
        minVal = mc.intFieldGrp(args[2], q=True, v1=True)
        maxVal = mc.intFieldGrp(args[2], q=True, v2=True)
        mc.deleteUI(args[0], window=True)

        self.AddShot(name, minVal, maxVal)

    def AddShot(self, name, minVal, maxVal):
        # create if not found
        if not self.animListNode:
            self.animListNode = cgmMeta.cgmObject(name="AnimListNode")#node.Transform(name="AnimListNode")
            self.animListNode.addAttr("subAnimList", attrType = 'string')

        self.animDict[name] = [minVal, maxVal, maxVal - minVal]
        self.animListNode.subAnimList =  self.animDict#json.dumps(self.animDict)

        self.Sort(self.sortType)

    def RefreshUI(self, *args):
        mc.deleteUI( self.window, window=True )
        self.CreateWindow()

    def RefreshShotListUI(self, *args):
        self.LoadAnimList()
        self.Sort(self.sortType)
        self.RefreshShotList()

    def RefreshShotList(self, *args):
        children = mc.columnLayout(self.shotRCL, q=True, childArray=True)
        for child in children if children else []:
            mc.deleteUI(child)

        self.animUIDict = {}

        mc.setParent(self.shotRCL)

        # subAnims
        for item in self.animList:
            key = item[0]

            self.animUIDict[key] = {}

            # One MelHSingleStretchLayout per shot: every sibling keeps its original fixed
            # pixel width (int-cast off self._colWidths, matching the header above), and the
            # nameField is the single stretch widget that absorbs resize space.
            # h=25 (the row's tallest child, the removeBtn MelIconButton below) is set
            # explicitly: this is a formLayout-based row (_AlignedFormLayout) with no
            # inherent height of its own, so without an explicit h= it can render taller
            # than its widgets' actual ~24px height, leaving blank space inside the row
            # that looks like extra spacing between shots.
            _row = mUI.MelHSingleStretchLayout(self.shotRCL, ut='cgmUITemplate', padding=0, h=25)

            # Use mUI.MelTextField (a proper BaseMelWidget subclass) instead of raw mc.textField:
            # BaseMelWidget.__new__ assigns a short/leaf unique name (matching every other
            # mUI.Mel* sibling in this row), whereas raw mc.textField(...) returns the full long
            # UI path. MelHSingleStretchLayout.layout() resolves its children via short/leaf
            # names (-childArray query), so a long-path stretch widget fails the
            # children.index(stretchWidget) lookup in setStretchWidget() below.
            # bgc=[1,1,1] is explicit here rather than relying on ut='cgmUITemplate': the
            # cgmUITemplate dt= entry in GuiFactory.initializeTemplates() only covers
            # mc.textField (white bg), not mc.intField at all, so MelIntField needs its
            # own explicit white background to match.
            self.animUIDict[key]['nameField'] = mUI.MelTextField(_row, text=key, bgc=[1,1,1], changeCommand=partial(self.RenameShot, key))
            self.animUIDict[key]['minButton'] = mUI.MelButton(_row, ut='cgmUITemplate', label="<", w=int(self._colWidths[1][1]), command=partial(self.SetShotRange, key, max=False) )
            self.animUIDict[key]['minField'] = mUI.MelIntField(_row, v = item[1][0], w=int(self._colWidths[2][1]), bgc=[1,1,1], changeCommand=partial(self.AdjustShotRange, key) )
            self.animUIDict[key]['maxField'] = mUI.MelIntField(_row, v = item[1][1], w=int(self._colWidths[3][1]), bgc=[1,1,1], changeCommand=partial(self.AdjustShotRange, key) )
            self.animUIDict[key]['maxButton'] = mUI.MelButton(_row, ut='cgmUITemplate', label=">", w=int(self._colWidths[4][1]), command=partial(self.SetShotRange, key, min=False) )
            self.animUIDict[key]['lengthField'] = mUI.MelIntField(_row, v = item[1][2], w=int(self._colWidths[5][1]), bgc=[1,1,1], changeCommand=partial(self.AdjustShotLength, key) )
            self.animUIDict[key]['frameBtn'] = mUI.MelButton(_row, ut='cgmUITemplate', label="Frame", w=int(self._colWidths[6][1]), command=partial(self.SetShotRange, key) )
            # MelSpacer.__new__ only takes (parent, w, h) - no bgc passthrough (same pitfall
            # documented on the header row above) - so these two inter-column placeholders use
            # MelLabel (MelSpacer's own base class, same WIDGET_CMD = mc.text) instead, and are
            # kept in animUIDict so UpdateShotList can recolor them with the rest of the row for
            # a continuous highlight band instead of a white gap.
            self.animUIDict[key]['spacer1'] = mUI.MelLabel(_row, l='', bgc=[1,1,1], w=int(self._colWidths[7][1]), h=1)
            self.animUIDict[key]['removeBtn'] = mUI.MelIconButton(_row,
                                                                    ut='cgmUITemplate',
                                                                    ann='Remove shot',
                                                                    image=os.path.join(cgmUI._path_imageFolder, 'clear.png'),
                                                                    w=25, h=25,
                                                                    bgc=cgmUI.guiButtonColor,
                                                                    style='iconOnly',
                                                                    c=partial(self.RemoveShot, key))
            self.animUIDict[key]['spacer2'] = mUI.MelLabel(_row, l='', bgc=[1,1,1], w=int(self._colWidths[9][1]), h=1)

            _row.setStretchWidget(self.animUIDict[key]['nameField'])
            _row.layout()

            self._defaultBGColor = mc.textField(self.animUIDict[key]['nameField'], q=True, backgroundColor=True)
            # minButton/maxButton/frameBtn are mc.button underneath (MelButton); cgmUITemplate's
            # dt= entry for mc.button sets its own default backgroundColor (see guiButtonColor
            # usage above) - capture it here the same way _defaultBGColor is captured for the
            # text/int fields, so UpdateShotList has a real revert color instead of guessing one.
            self._defaultButtonBGColor = mc.button(self.animUIDict[key]['minButton'], q=True, backgroundColor=True)
            # spacer1/spacer2 are mc.text underneath (MelLabel); capture their default bg too.
            self._defaultSpacerBGColor = mc.text(self.animUIDict[key]['spacer1'], q=True, backgroundColor=True)

        self.UpdateShotList()
        
    def UpdateShotList(self):
        minV = mc.playbackOptions(q=True, min=True)
        maxV = mc.playbackOptions(q=True, max=True)

        for key in self.animDict:
            mc.textField(self.animUIDict[key]['nameField'], e=True, text=key )
            mc.intField(self.animUIDict[key]['minField'], e=True, v=self.animDict[key][0] )
            mc.intField(self.animUIDict[key]['maxField'], e=True, v=self.animDict[key][1] )
            mc.intField(self.animUIDict[key]['lengthField'], e=True, v=self.animDict[key][2] )
            mc.button(self.animUIDict[key]['minButton'], e=True, command=partial(self.SetShotRange, key, max=False) )
            mc.button(self.animUIDict[key]['maxButton'], e=True, command=partial(self.SetShotRange, key, min=False) )

            # Set Colors
            # Single whole-row condition drives the highlight for every control in the row -
            # text/int fields, buttons, and the inter-column spacers - so an in-range shot reads
            # as one continuous teal band instead of alternating teal/white segments (minField/
            # maxField used to key off their OWN exact-match-to-playback-range condition, which
            # is a different, narrower test than "whole shot range is within playback range" and
            # is what produced the patchy look). The old exact-match tests on minField/maxField
            # (minV == shot start / maxV == shot end) were a separate "which field defines the
            # current playback range" cue layered on top; dropped here rather than kept as a
            # second overriding color, since the user's reference screenshot shows one uniform
            # band with no distinct sub-highlight, and layering it back in would just reintroduce
            # the same patchiness for rows where only one of the two exactly matches.
            highlightColor = [.2, .3, .3]
            inRange = self.animDict[key][0] >= minV and self.animDict[key][1] <= maxV

            fieldColor = highlightColor if inRange else self._defaultBGColor
            buttonColor = highlightColor if inRange else self._defaultButtonBGColor
            spacerColor = highlightColor if inRange else self._defaultSpacerBGColor

            mc.textField(self.animUIDict[key]['nameField'], e=True, backgroundColor=fieldColor )
            mc.intField(self.animUIDict[key]['minField'], e=True, backgroundColor=fieldColor )
            mc.intField(self.animUIDict[key]['maxField'], e=True, backgroundColor=fieldColor )
            mc.intField(self.animUIDict[key]['lengthField'], e=True, backgroundColor=fieldColor )

            # minButton/maxButton/frameBtn are MelButton (mc.button underneath) - backgroundColor
            # is the same edit-mode kwarg already used elsewhere in this file for plain mc.button
            # edits (e.g. command= on these same controls above), so no new API needed here.
            mc.button(self.animUIDict[key]['minButton'], e=True, backgroundColor=buttonColor )
            mc.button(self.animUIDict[key]['maxButton'], e=True, backgroundColor=buttonColor )
            mc.button(self.animUIDict[key]['frameBtn'], e=True, backgroundColor=buttonColor )

            # spacer1/spacer2 are MelLabel (mc.text underneath) - color them the same way so the
            # gaps between fields/buttons read as part of the continuous band, not white breaks.
            mc.text(self.animUIDict[key]['spacer1'], e=True, backgroundColor=spacerColor )
            mc.text(self.animUIDict[key]['spacer2'], e=True, backgroundColor=spacerColor )

    def AdjustShotRange(self, *args):
        shift = 0

        minVal = mc.intField( self.animUIDict[args[0]]['minField'], q=True, v=True )
        maxVal = mc.intField( self.animUIDict[args[0]]['maxField'], q=True, v=True )

        length = maxVal - minVal

        if self.animDict[args[0]][0] != minVal:
            shift = minVal - self.animDict[args[0]][0]
            maxVal = minVal + self.animDict[args[0]][2]
            length = maxVal - minVal
        elif self.animDict[args[0]][1] != maxVal:
            shift = maxVal - self.animDict[args[0]][1]
        elif self.animDict[args[0]][2] != length:
            shift = length - self.animDict[args[0]][2]

        self.animDict[args[0]][0] = minVal
        self.animDict[args[0]][1] = maxVal
        self.animDict[args[0]][2] = maxVal - minVal

        mc.intField( self.animUIDict[args[0]]['lengthField'], e=True, v=self.animDict[args[0]][2] )

        if mc.menuItem(self.autoAdjustFramesMI, q=True, checkBox=True ) and shift != 0:
            self.ShiftTimeRanges(minVal, shift, ignoreKeys = [args[0]])
        
        self.animListNode.subAnimList = self.animDict#json.dumps(self.animDict)
        
        self.UpdateShotList()

    def AdjustShotLength(self, *args):

        shotLength = mc.intField( self.animUIDict[args[0]]['lengthField'], q=True, v=True )

        shift = shotLength - self.animDict[args[0]][2]
        
        self.animDict[args[0]][1] = self.animDict[args[0]][0] + shotLength
        self.animDict[args[0]][2] = shotLength

        shotLength = mc.intField( self.animUIDict[args[0]]['maxField'], e=True, v=self.animDict[args[0]][1] )

        if mc.menuItem(self.autoAdjustFramesMI, q=True, checkBox=True ) and shift != 0:
            self.ShiftTimeRanges(self.animDict[args[0]][0], shift, ignoreKeys = [args[0]])
        
        self.animListNode.subAnimList = self.animDict#json.dumps(self.animDict)
        self.UpdateShotList()

    def ShiftTimeRanges(self, startTime, shift, ignoreKeys = []):
        for key in self.animDict:
            if key in ignoreKeys:
                continue

            if self.animDict[key][0] >= startTime:
                self.animDict[key][0] += shift
                self.animDict[key][1] += shift
            elif self.animDict[key][1] > startTime:
                self.animDict[key][1] += shift

            self.animDict[key][2] = self.animDict[key][1] - self.animDict[key][0]

        self.UpdateShotList()

    def RenameShot(self, *args):
        key = args[0]

        newName = str(mc.textField(self.animUIDict[key]['nameField'], q=True, text=True).strip())
        
        if newName == key:
            return

        if newName in self.animDict:
            mc.textField(self.animUIDict[key]['nameField'], e=True, text=key)
            mc.confirmDialog(title="Name Conflict", message='Sorry, new name conflicts with an existing name', button=['Bummer'])
            return
            
        self.animDict[newName] = self.animDict.pop(key)        
        self.animUIDict[newName] = self.animUIDict.pop(key)

        self.animListNode.subAnimList = self.animDict#json.dumps(self.animDict)

        # Adjust UI elements to reflect new name
        mc.textField(self.animUIDict[newName]['nameField'], e=True, changeCommand=partial(self.RenameShot, newName))
        mc.intField(self.animUIDict[newName]['minField'], e=True, changeCommand=partial(self.AdjustShotRange, newName) )
        mc.intField(self.animUIDict[newName]['maxField'], e=True, changeCommand=partial(self.AdjustShotRange, newName) )
        mc.intField(self.animUIDict[newName]['lengthField'], e=True, changeCommand=partial(self.AdjustShotLength, newName) )
        mc.button(self.animUIDict[newName]['frameBtn'], e=True, command=partial(self.SetShotRange, newName) )
        mc.iconTextButton(self.animUIDict[newName]['removeBtn'], e=True, command=partial(self.RemoveShot, newName))
        mc.button(self.animUIDict[newName]['minButton'], e=True, command=partial(self.SetShotRange, newName, max=False) )
        mc.button(self.animUIDict[newName]['maxButton'], e=True, command=partial(self.SetShotRange, newName, min=False) )

    def LoadAnimList(self):
        # Find anim list node
        animListNodes = mc.ls("*.subAnimList")
        if len(animListNodes) > 0:
            self.animListNode = cgmMeta.asMeta(animListNodes)[0]
            animListString = self.animListNode.subAnimList
            if animListString:
                self.animDict = animListString#json.loads(animListString)

                for key in self.animDict:
                    if len(self.animDict[key]) == 2:
                        self.animDict[key].append(self.animDict[key][1] - self.animDict[key][0])
class AnimList(object):
    def __init__(self):
        self.shotDict = {}
        self.shotList = []
        
        animListNodes = mc.ls("*.subAnimList")
        if len(animListNodes) > 0:
            animListNode = cgmMeta.asMeta(animListNodes)[0]
            animListString = animListNode.subAnimList
            if animListString:
                #the try here is for the older version of the data object before moving to cgm methods
                try:self.shotDict = json.loads(animListString)
                except:
                    self.shotDict = animListString
                    #for k,v in animListString.iteritems():
                    #    self.shotDict.append([k,v])
                    #self.shotDict = animListString
                    

        self.SortedList(1)

    def SortedList(self, sortType = 1):
        if sortType == 0:
            self.shotList = sorted(list(self.shotDict.items()), key=operator.itemgetter(0))
        elif sortType == 1:
            self.shotList = sorted(list(self.shotDict.items()), key=lambda x: x[1][0])
        elif sortType == 2:
            self.shotList = sorted(list(self.shotDict.items()), key=lambda x: x[1][1]) 
        elif sortType == 3:
            self.shotList = sorted(list(self.shotDict.items()), key=lambda x: x[1][2])

        return self.shotList