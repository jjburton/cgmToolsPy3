#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# Tools
#>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

#>>>======================================================================
import logging
import importlib
logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
#=========================================================================

import cgm.core.cgm_General as cgmGEN
import webbrowser
import maya.mel as mel

def red9( *a ):
    import Red9
    importlib.reload(Red9)
    Red9.start()

def attrTools( *a ):
    from cgm.core.tools import attrTools as attrTools
    importlib.reload(attrTools)
    attrTools.ui()

def cgmMeshTools( *a ):
    from cgm.core.tools import meshTools
    importlib.reload(meshTools)
    cgmMeshToolsWin = meshTools.run()
    
def mrsUI():
    try:
        import cgm.core.mrs.Builder as MRSBUILDER
        importlib.reload(MRSBUILDER)
        #MRSBUILDER.ui()
        MRSBUILDER.ui_get()
    except Exception as err:
        cgmGEN.cgmException(Exception,err)
        
def mrsBlockEditor():
    import cgm.core.mrs.Builder as MRSBUILDER
    MRSBUILDER.blockEditor_get()
    
def mrsBlockCreate():
    import cgm.core.mrs.Builder as MRSBUILDER
    importlib.reload(MRSBUILDER)
    MRSBUILDER.ui_createBlock()
    
def mrsBlockPicker():
    import cgm.core.mrs.Builder as MRSBUILDER
    MRSBUILDER.blockPicker_get()        
    
def mrsANIMATE():
    import cgm.core.mrs.Animate as MRSANIMATE
    importlib.reload(MRSANIMATE)
    MRSANIMATE.ui()
    
def mrsPOSER():
    import cgm.core.mrs.PoseManager as MRSPOSER
    importlib.reload(MRSPOSER)
    MRSPOSER.ui()
    
def cgmSnapTools():
    try:
        import cgm.core.tools.snapTools as SNAP
        importlib.reload(SNAP)
        SNAP.ui()
    except Exception as err:
        cgmGEN.cgmExceptCB(Exception,err)
        
def mocapBakeTool():
    try:
        import cgm.core.tools.mocapBakeTools as MOCAPBAKE
        importlib.reload(MOCAPBAKE)
        MOCAPBAKE.ui()
    except Exception as err:
        cgmGEN.cgmExceptCB(Exception,err)
        
def cgmUpdateTool():
    try:
        import cgm.core.tools.updateTool as CGMUPDATE
        importlib.reload(CGMUPDATE)
        CGMUPDATE.ui()
    except Exception as err:
        cgmGEN.cgmExceptCB(Exception,err)
        
def cgmUpdateTool_lastBranch():
    try:
        import cgm.core.tools.updateTool as CGMUPDATE
        importlib.reload(CGMUPDATE)
        CGMUPDATE.checkBranch()
    except Exception as err:
        cgmGEN.cgmExceptCB(Exception,err)
        
def locinator():
    from cgm.core.tools import locinator as LOCINATOR
    importlib.reload(LOCINATOR)
    LOCINATOR.ui()

def dynParentTool( *a ):
    from cgm.core.tools import dynParentTool as DYNPARENTTOOL
    importlib.reload(DYNPARENTTOOL)
    DYNPARENTTOOL.ui()
    
def setTools():
    import cgm.core.tools.setTools as SETTOOLS
    importlib.reload(SETTOOLS)
    SETTOOLS.ui()
    
def transformTools():
    import cgm.core.tools.transformTools as TT
    importlib.reload(TT)
    TT.ui()
    
def jointTools():
    import cgm.core.tools.jointTools as JOINTTOOLS
    importlib.reload(JOINTTOOLS)
    JOINTTOOLS.ui()

def ngskin():
    try:
        from ngSkinTools.ui.mainwindow import MainWindow
        MainWindow.open()    
    except Exception as err:
        webbrowser.open("http://www.ngskintools.com/")
        raise ValueError("Failed to load. Go get it. | {0}".format(err))

def SVGator():
    import cgm.core.tools.SVGator as SVGATOR
    importlib.reload(SVGATOR)
    SVGATOR.ui()
    
    
def CGMDATui():
    import cgm.core.cgm_Dat as CGMDAT
    importlib.reload(CGMDAT)
    CGMDAT.ui()
    
def BLOCKDATui():
    import cgm.core.mrs.MRSDat as MRSDAT
    importlib.reload(MRSDAT)
    MRSDAT.uiBlockDat()
    
def CONFIGDATui():
    import cgm.core.mrs.MRSDat as MRSDAT
    importlib.reload(MRSDAT)
    MRSDAT.uiBlockConfigDat()
    
def SHAPEDATui():
    import cgm.core.mrs.MRSDat as MRSDAT
    importlib.reload(MRSDAT)
    MRSDAT.uiShapeDat()
    
def mrsShots():
    try:
        import cgm.core.mrs.Shots as SHOTS
        importlib.reload(SHOTS)
        x = SHOTS.ShotUI()
    except Exception as err:
        cgmGEN.cgmException(Exception,err)

def mrsScene():
    try:
        import cgm.core.mrs.Scene as SCENE
        importlib.reload(SCENE)
        #mel.eval('python "import cgm.core.mrs.Scene as SCENE;cgmSceneUI = SCENE.ui()"')
        SCENE.ui()
    except Exception as err:
        cgmGEN.cgmException(Exception,err)
        
def mrsSceneLegacy():
    import cgm.core.mrs.SceneOld as SCENELEGACY
    importlib.reload(SCENELEGACY)
    #mel.eval('python "import cgm.core.mrs.Scene as SCENE;cgmSceneUI = SCENE.ui()"')
    SCENELEGACY.ui()

        
def mrsShapeDat():
    import cgm.core.mrs.MRSDat as MRSDAT
    importlib.reload(MRSDAT)
    MRSDAT.uiShapeDat()
        
def animDraw():
    try:
        import cgm.core.tools.liveRecord as liveRecord
        importlib.reload(liveRecord)
        import cgm.core.tools.animDrawTool as ADT
        importlib.reload(ADT)
        import cgm.core.tools.animDraw as animDraw
        importlib.reload(animDraw)        
        mel.eval('python "import cgm.core.tools.animDrawTool as ANIMDRAW;cgmAnimDrawUI = ANIMDRAW.ui()"')
    except Exception as err:
        cgmGEN.cgmException(Exception,err)
        
        
def animFilter():
    try:
        import cgm.core.tools.animFilterTool as ANIMFILTER
        importlib.reload(ANIMFILTER)
        mel.eval('python "import cgm.core.tools.animFilterTool as ANIMFILTER;cgmAnimFilterUI = ANIMFILTER.ui()"')
    except Exception as err:
        cgmGEN.cgmException(Exception,err)
        

    #except Exception,err:
    #    log.warning("[mrsScene] failed to load. | {0}".format(err))
def cgmSimChain():
    try:
        from cgm.core.tools import dynFKTool
        importlib.reload(dynFKTool)
        dynFKTool.ui()
    except Exception as err:
        cgmGEN.cgmException(Exception,err)
        

def cgmProject():
    try:
        import cgm.core.tools.Project as PROJECT
        importlib.reload(PROJECT)
        importlib.reload(PROJECT.PU)
        #x = PROJECT.ui()
        mel.eval('python "import cgm;uiProject = cgm.core.tools.Project.ui();"')
        
    except Exception as err:
        cgmGEN.cgmException(Exception,err)
    #except Exception,err:
    #    log.warning("[cgmProject] failed to load. | {0}".format(err))
    #    raise Exception,err

def loadPuppetBox( *a ):
    from cgm.tools import puppetBox
    importlib.reload(puppetBox)
    cgmPuppetBoxWin = puppetBox.run()

def loadPuppetBox2( *a ):
    from cgm.tools import puppetBox2
    importlib.reload(puppetBox2)
    cgmPuppetBoxWin = puppetBox2.run()	

def loadCGMSimpleGUI( *a ):
    try:
        
        from cgm.core.classes import GuiFactory as uiFactory
        importlib.reload(uiFactory)
        uiFactory.cgmGUI()
    except Exception as err:
        cgmGEN.cgmException(Exception,err)        

def reload_cgmCore( *a ):
    try:
        import cgm.core
        cgm.core._reload()	
    except Exception as err:
        cgmGEN.cgmException(Exception,err)

def testMorpheus( *a ):
    from cgm.core.tests import cgmMeta_test as testCGM
    importlib.reload(testCGM)
    testCGM.MorpheusBase_Test()


#Zoo stuff =====================================================================
def loadZooToolbox( *a ):
    import zooToolbox
    zooToolbox.ToolboxWindow()

def loadSkinPropagation( *a ):
    from cgm.lib.zoo.zooPyMaya import refPropagation
    refPropagation.propagateWeightChangesToModel_confirm()

def loadXferAnim( *a ):
    from cgm.lib.zoo.zooPyMaya import xferAnimUI
    xferAnimUI.XferAnimWindow()
    
    

#>>Legacy Tools =======================================================================================
def attrToolsLEGACY( *a ):
    from cgm.tools import attrTools as attrTools1
    importlib.reload(attrTools1)
    cgmAttrToolsWin = attrTools1.run()
    
def animToolsLEGACY( *a ):
    from cgm.tools import animTools
    importlib.reload(animTools)
    cgmAnimToolsWin = animTools.run()

def setToolsLEGACY( *a ):
    from cgm.tools import setTools
    importlib.reload(setTools)
    cgmSetToolsWin = setTools.run()	
    
    
def locinatorLEGACY( *a ):
    from cgm.tools import locinator
    importlib.reload(locinator)
    locinator.run()
    
def tdToolsLEGACY( *a ):
    import maya.cmds as mc
    import maya.mel as mel
    mel.eval('python("import maya.cmds as mc;")')
    from cgm.tools import tdTools
    importlib.reload(tdTools)
    tdTools.run()
