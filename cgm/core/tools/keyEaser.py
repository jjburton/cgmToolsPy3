"""
------------------------------------------
baseTool: cgm.core.tools
Author: Josh Burton
email: cgmonks.info@gmail.com

Website : https://github.com/jjburton/cgmTools/wiki
------------------------------------------
Example ui to start from
================================================================
"""
# From Python =============================================================
from collections import deque
import copy
import logging
import math

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

import maya.cmds as mc

import cgm.core.classes.GuiFactory as cgmUI
from cgm.core import cgm_RigMeta as cgmRigMeta

mUI = cgmUI.mUI

from cgm.core.lib import shared_data as SHARED
from cgm.core.cgmPy import validateArgs as VALID
from cgm.core import cgm_General as cgmGEN
from cgm.core import cgm_Meta as cgmMeta
import cgm.core.lib.transform_utils as TRANS
from cgm.core.cgmPy import path_Utils as CGMPATH
import cgm.core.lib.math_utils as MATH
from cgm.lib import lists
from cgm.core.lib import noise


# >>> Root settings =============================================================
__version__ = cgmGEN.__RELEASESTRING
__toolname__ = "keaser"


class ui(cgmUI.cgmGUI):
    USE_Template = "cgmUITemplate"
    WINDOW_NAME = "{0}_ui".format(__toolname__)
    WINDOW_TITLE = "{1} - {0}".format(__version__, __toolname__)
    DEFAULT_MENU = None
    RETAIN = True
    MIN_BUTTON = True
    MAX_BUTTON = False
    FORCE_DEFAULT_SIZE = (
        True  # always resets the size of the window when its re-created
    )
    DEFAULT_SIZE = 425, 190
    TOOLNAME = "{0}.ui".format(__toolname__)
    UNDO_CHUNK_NAME = "undo-keyser-drag"

    def insert_init(self, *args, **kws):
        _str_func = "__init__[{0}]".format(self.__class__.TOOLNAME)
        log.info("|{0}| >>...".format(_str_func))

        if kws:
            log.debug("kws: %s" % str(kws))
        if args:
            log.debug("args: %s" % str(args))
        log.info(self.__call__(q=True, title=True))

        self.__version__ = __version__
        self.__toolName__ = self.__class__.WINDOW_NAME

        self._isChunkOpen = False
        self._selected_objects = []

        # self.l_allowedDockAreas = []
        self.WINDOW_TITLE = self.__class__.WINDOW_TITLE
        self.DEFAULT_SIZE = self.__class__.DEFAULT_SIZE

    def build_menus(self):
        self.uiMenu_FirstMenu = mUI.MelMenu(
            l="Setup", pmc=cgmGEN.Callback(self.buildMenu_first)
        )

    def buildMenu_first(self):
        self.uiMenu_FirstMenu.clear()
        # >>> Reset Options

        mUI.MelMenuItemDiv(self.uiMenu_FirstMenu)

        mUI.MelMenuItem(
            self.uiMenu_FirstMenu,
            l="Reload",
            c=lambda *a: mc.evalDeferred(self.reload, lp=True),
        )

        mUI.MelMenuItem(
            self.uiMenu_FirstMenu,
            l="Reset",
            c=lambda *a: mc.evalDeferred(self.reload, lp=True),
        )

    def build_layoutWrapper(self, parent):
        _str_func = "build_layoutWrapper"

        _MainForm = mUI.MelFormLayout(self, ut="cgmUITemplate")
        _column = self.buildColumn_main(_MainForm)

        _row_cgm = cgmUI.add_cgmFooter(_MainForm)
        _MainForm(
            edit=True,
            af=[
                (_column, "top", 0),
                (_column, "left", 0),
                (_column, "right", 0),
                (_row_cgm, "left", 0),
                (_row_cgm, "right", 0),
                (_row_cgm, "bottom", 0),
            ],
            ac=[
                (_column, "bottom", 2, _row_cgm),
            ],
            attachNone=[(_row_cgm, "top")],
        )

    def buildColumn_main(self, parent):
        mc.setParent(parent)
        self.uiTabLayout = mc.tabLayout()
        print("My tab layout -- %s" % self.uiTabLayout)

        self.easeColumn = self.buildColumn_ease(self.uiTabLayout, asScroll=True)
        self.noiseColumn = self.buildColumn_noise(self.uiTabLayout, asScroll=True)
        self.springColumn = self.buildColumn_spring(self.uiTabLayout, asScroll=True)
        self.offsetColumn = self.buildColumn_offset(self.uiTabLayout, asScroll=True)

        mc.tabLayout(
            self.uiTabLayout,
            edit=True,
            tabLabel=(
                (self.easeColumn, "Take It Easy"),
                (self.noiseColumn, "Bring The Noise"),
                (self.springColumn, "Spring To Action"),
                (self.offsetColumn, "Set It Off"),
            ),
            cc=lambda *a: mc.evalDeferred(
                cgmGEN.Callback(self.uiFunc_handleTabChange), lp=True
            ),
        )

        return self.uiTabLayout

    def uiFunc_handleTabChange(self):
        print("Tab changed")

    #############################################
    # Ease
    #############################################
    def buildColumn_ease(self, parent, asScroll=False):
        if asScroll:
            _inside = mUI.MelScrollLayout(parent, useTemplate="cgmUISubTemplate")
        else:
            _inside = mUI.MelColumnLayout(parent, useTemplate="cgmUISubTemplate")

        defaultFavor = 0.5
        defaultMidPoint = 0.5

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Favor:", align="right")
        self.uiTF_favor = mUI.MelFloatField(
            _row, minValue=0.0, value=defaultFavor, precision=2, annotation="Favor"
        )
        self.uiTF_favor(
            edit=True,
            changeCommand=cgmGEN.Callback(self.uiFunc_setFavorSlider, "field"),
        )

        self.uiSlider_favor = mUI.MelFloatSlider(
            _row, 0.0, 1.0, defaultFavor, step=0.01
        )
        self.uiSlider_favor.setValue(defaultFavor)
        cmd = cgmGEN.Callback(self.uiFunc_setFavorSlider, "slider")

        self.uiSlider_favor(
            edit=True, changeCommand=cgmGEN.Callback(self.uiFunc_handleChange, cmd)
        )
        self.uiSlider_favor(
            edit=True, dragCommand=cgmGEN.Callback(self.uiFunc_handleDrag, cmd)
        )

        _row.setStretchWidget(self.uiSlider_favor)
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Midpoint:", align="right")
        self.uiTF_midPoint = mUI.MelFloatField(
            _row,
            minValue=0.0,
            value=defaultMidPoint,
            precision=2,
            annotation="Midpoint",
        )

        self.uiTF_midPoint(
            edit=True,
            changeCommand=cgmGEN.Callback(self.uiFunc_setMidPointSlider, "field"),
        )

        self.uiSlider_midPoint = mUI.MelFloatSlider(
            _row, 0.0, 1.0, defaultMidPoint, step=0.01
        )
        self.uiSlider_midPoint.setValue(defaultMidPoint)
        cmd = cgmGEN.Callback(self.uiFunc_setMidPointSlider, "slider")

        self.uiSlider_midPoint(
            edit=True, changeCommand=cgmGEN.Callback(self.uiFunc_handleChange, cmd)
        )
        self.uiSlider_midPoint(
            edit=True, dragCommand=cgmGEN.Callback(self.uiFunc_handleDrag, cmd)
        )

        _row.setStretchWidget(self.uiSlider_midPoint)
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        return _inside

    #############################################
    # Noise
    #############################################
    def buildColumn_noise(self, parent, asScroll=False):
        if asScroll:
            _inside = mUI.MelScrollLayout(parent, useTemplate="cgmUISubTemplate")
        else:
            _inside = mUI.MelColumnLayout(parent, useTemplate="cgmUISubTemplate")

        defaultAmplitude = 5
        defaultFrequency = 0.5

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Amplitude:", align="right")
        self.uiTF_noise_amplitude = mUI.MelFloatField(
            _row,
            minValue=0.0,
            value=defaultAmplitude,
            precision=2,
            annotation="Amplitude",
        )
        self.uiTF_noise_amplitude(
            edit=True,
            changeCommand=cgmGEN.Callback(self.uiFunc_setAmplitudeSlider, "field"),
        )

        self.uiSlider_noise_amplitude = mUI.MelFloatSlider(
            _row, 0.0, 10.0, defaultAmplitude, step=0.01
        )
        self.uiSlider_noise_amplitude.setValue(defaultAmplitude)
        cmd = cgmGEN.Callback(self.uiFunc_setAmplitudeSlider, "slider")

        self.uiSlider_noise_amplitude(
            edit=True, changeCommand=cgmGEN.Callback(self.uiFunc_handleChange, cmd)
        )
        self.uiSlider_noise_amplitude(
            edit=True, dragCommand=cgmGEN.Callback(self.uiFunc_handleDrag, cmd)
        )

        _row.setStretchWidget(self.uiSlider_noise_amplitude)
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Frequency:", align="right")
        self.uiTF_noise_frequency = mUI.MelFloatField(
            _row,
            minValue=0.0,
            value=defaultFrequency,
            precision=2,
            annotation="Frequency",
        )

        self.uiTF_noise_frequency(
            edit=True,
            changeCommand=cgmGEN.Callback(self.uiFunc_setFrequencySlider, "field"),
        )

        self.uiSlider_noise_frequency = mUI.MelFloatSlider(
            _row, 0.0, 1.0, defaultFrequency, step=0.01
        )
        self.uiSlider_noise_frequency.setValue(defaultFrequency)
        cmd = cgmGEN.Callback(self.uiFunc_setFrequencySlider, "slider")

        self.uiSlider_noise_frequency(
            edit=True, changeCommand=cgmGEN.Callback(self.uiFunc_handleChange, cmd)
        )
        self.uiSlider_noise_frequency(
            edit=True, dragCommand=cgmGEN.Callback(self.uiFunc_handleDrag, cmd)
        )

        _row.setStretchWidget(self.uiSlider_noise_frequency)
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        return _inside

    #############################################
    # Spring
    #############################################
    def buildColumn_spring(self, parent, asScroll=False):
        if asScroll:
            _inside = mUI.MelScrollLayout(parent, useTemplate="cgmUISubTemplate")
        else:
            _inside = mUI.MelColumnLayout(parent, useTemplate="cgmUISubTemplate")

        defaultDamp = 0.5
        defaultFrequency = 0.5

        cmd = cgmGEN.Callback(self.uiFunc_setSpringDampSlider, "slider")

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)

        mUI.MelLabel(_row, l="Use Last Key As Target:", align="right")

        _row.setStretchWidget(mUI.MelSeparator(_row, w=2))

        self.uiSpringLastKeyCB = mUI.MelCheckBox(
            _row,
            useTemplate="cgmUITemplate",
            v=False,
            en=True,
            changeCommand=cmd,
        )

        mUI.MelSpacer(_row, w=5)
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Damp:", align="right")
        self.uiTF_spring_damp = mUI.MelFloatField(
            _row, minValue=0.0, value=defaultDamp, precision=2, annotation="Damp"
        )
        self.uiTF_spring_damp(
            edit=True,
            changeCommand=cgmGEN.Callback(self.uiFunc_setSpringDampSlider, "field"),
        )

        self.uiSlider_spring_damp = mUI.MelFloatSlider(
            _row, 0.0, 1.0, defaultDamp, step=0.01
        )
        self.uiSlider_spring_damp.setValue(defaultDamp)

        self.uiSlider_spring_damp(
            edit=True, changeCommand=cgmGEN.Callback(self.uiFunc_handleChange, cmd)
        )
        self.uiSlider_spring_damp(
            edit=True, dragCommand=cgmGEN.Callback(self.uiFunc_handleDrag, cmd)
        )

        _row.setStretchWidget(self.uiSlider_spring_damp)
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Frequency:", align="right")
        self.uiTF_spring_frequency = mUI.MelFloatField(
            _row,
            minValue=0.0,
            value=defaultFrequency,
            precision=2,
            annotation="Frequency",
        )

        self.uiTF_spring_frequency(
            edit=True,
            changeCommand=cgmGEN.Callback(
                self.uiFunc_setSpringFrequencySlider, "field"
            ),
        )

        self.uiSlider_spring_frequency = mUI.MelFloatSlider(
            _row, 0.0, 10.0, defaultFrequency, step=0.01
        )
        self.uiSlider_spring_frequency.setValue(defaultFrequency)
        cmd = cgmGEN.Callback(self.uiFunc_setSpringFrequencySlider, "slider")

        self.uiSlider_spring_frequency(
            edit=True, changeCommand=cgmGEN.Callback(self.uiFunc_handleChange, cmd)
        )
        self.uiSlider_spring_frequency(
            edit=True, dragCommand=cgmGEN.Callback(self.uiFunc_handleDrag, cmd)
        )

        _row.setStretchWidget(self.uiSlider_spring_frequency)
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        return _inside

    #############################################
    # Offset
    #############################################
    def buildColumn_offset(self, parent, asScroll=False):
        if asScroll:
            _inside = mUI.MelScrollLayout(parent, useTemplate="cgmUISubTemplate")
        else:
            _inside = mUI.MelColumnLayout(parent, useTemplate="cgmUISubTemplate")

        defaultOffset = 0.0

        _row = mUI.MelHSingleStretchLayout(_inside, expand=True, ut="cgmUISubTemplate")
        mUI.MelSpacer(_row, w=5)
        mUI.MelLabel(_row, l="Offset:", align="right")
        self.uiTF_offset = mUI.MelFloatField(
            _row, minValue=0.0, value=defaultOffset, precision=2, annotation="Offset"
        )
        self.uiTF_offset(
            edit=True,
            changeCommand=cgmGEN.Callback(self.uiFunc_setOffsetSlider, "field"),
        )

        self.uiSlider_offset = mUI.MelFloatSlider(
            _row, 0.0, 1.0, defaultOffset, step=0.01
        )
        self.uiSlider_offset.setValue(defaultOffset)
        cmd = cgmGEN.Callback(self.uiFunc_setOffsetSlider, "slider")

        self.uiSlider_offset(
            edit=True, changeCommand=cgmGEN.Callback(self.uiFunc_handleChange, cmd)
        )
        self.uiSlider_offset(
            edit=True, dragCommand=cgmGEN.Callback(self.uiFunc_handleDrag, cmd)
        )

        _row.setStretchWidget(self.uiSlider_offset)
        mUI.MelSpacer(_row, w=5)
        _row.layout()

        return _inside

    def uiFunc_handleDrag(self, func):
        if not self._isChunkOpen:
            mc.undoInfo(openChunk=True, chunkName=self.UNDO_CHUNK_NAME)
            self._isChunkOpen = True
            self._selected_objects = get_selected_keys()
            cmd = cgmGEN.Callback(self.uiFunc_closeChunk)
            self.scriptJobs = []
            self.scriptJobs.append(
                mc.scriptJob(e=["Undo", cmd], protected=True, ro=True)
            )
            self.scriptJobs.append(
                mc.scriptJob(e=["SelectionChanged", cmd], protected=True, ro=True)
            )

        func()

    def uiFunc_handleChange(self, func):
        func()

    def uiFunc_closeChunk(self):
        if self._isChunkOpen:
            mc.undoInfo(closeChunk=True)
            self._isChunkOpen = False
            self._selected_objects = []

    def uiFunc_setFavorSlider(self, source):
        uiFunc_setFieldSlider(self.uiTF_favor, self.uiSlider_favor, source, 1.0, 0.01)

        adjust_favoring(
            self._selected_objects,
            self.uiSlider_favor.getValue(),
            self.uiSlider_midPoint.getValue(),
        )

    def uiFunc_setMidPointSlider(self, source):
        uiFunc_setFieldSlider(
            self.uiTF_midPoint, self.uiSlider_midPoint, source, 1.0, 0.01
        )

        adjust_favoring(
            self._selected_objects,
            self.uiSlider_favor.getValue(),
            self.uiSlider_midPoint.getValue(),
        )

    def uiFunc_setAmplitudeSlider(self, source):
        uiFunc_setFieldSlider(
            self.uiTF_noise_amplitude, self.uiSlider_noise_amplitude, source, 10.0, 0.01
        )

        adjust_noise(
            self._selected_objects,
            self.uiSlider_noise_amplitude.getValue(),
            self.uiSlider_noise_frequency.getValue(),
        )

    def uiFunc_setFrequencySlider(self, source):
        uiFunc_setFieldSlider(
            self.uiTF_noise_frequency, self.uiSlider_noise_frequency, source, 1.0, 0.01
        )

        adjust_noise(
            self._selected_objects,
            self.uiSlider_noise_amplitude.getValue(),
            self.uiSlider_noise_frequency.getValue(),
        )

    def uiFunc_setSpringDampSlider(self, source):
        uiFunc_setFieldSlider(
            self.uiTF_spring_damp, self.uiSlider_spring_damp, source, 1.0, 0.01
        )

        adjust_spring(
            self._selected_objects,
            self.uiSlider_spring_damp.getValue(),
            self.uiSlider_spring_frequency.getValue(),
            self.uiSpringLastKeyCB.getValue(),
        )

    def uiFunc_setSpringFrequencySlider(self, source):
        uiFunc_setFieldSlider(
            self.uiTF_spring_frequency,
            self.uiSlider_spring_frequency,
            source,
            10.0,
            0.01,
        )

        adjust_spring(
            self._selected_objects,
            self.uiSlider_spring_damp.getValue(),
            self.uiSlider_spring_frequency.getValue(),
            self.uiSpringLastKeyCB.getValue(),
        )

    def uiFunc_setOffsetSlider(self, source):
        uiFunc_setFieldSlider(self.uiTF_offset, self.uiSlider_offset, source, 1.0, 0.01)

        adjust_offset(self._selected_objects, self.uiSlider_offset.getValue())


def uiFunc_setFieldSlider(field, slider, source, maxVal=100, step=1):
    _value = 0

    if source == "slider":
        _value = slider(query=True, value=True)
        field.setValue(_value)
    elif source == "field":
        _value = field.getValue()
        slider(edit=True, max=max(maxVal, _value))
        slider(edit=True, value=_value, step=step)

    return _value


def lerp(a, b, t):
    """
    Performs a linear interpolation between two values a and b using ratio t

    :param a: The start value
    :param b: The end value
    :param t: The ratio between a and b. 0 returns a, 1 returns b.
    :return: The interpolated value
    """
    return (1 - t) * a + t * b


def cubic_bezier(t, p0, p1, p2, p3, ease_factor):
    """
    A cubic Bezier curve interpolation function.
    :param t:  The interpolation alpha factor.
    :param p0: The first point (start point).
    :param p1: The second point (first control point).
    :param p2: The third point (second control point).
    :param p3: The fourth point (end point).
    :param ease_factor: The ease factor for "ease in" and "ease out" effects.
    :return:   The interpolated value.
    """
    u = 1.0 - t
    tt = t * t * t**ease_factor
    uu = u * u * u**ease_factor
    result = uu * p0  # for the beginning
    result += 3 * uu * t * p1  # Bezier control point 1
    result += 3 * u * tt * p2  # Bezier control point 2
    result += tt * p3  # for the end
    return result


def get_selected_keys():
    selected_keys = []

    # Get the list of all selected objects
    objects = mc.ls(selection=True)

    for obj in objects:
        # Initialize a new dictionary for this object
        object_dict = {obj: {}}

        # List all keyable attributes of the object
        keyable_attrs = mc.listAttr(obj, keyable=True)

        for attr in keyable_attrs:
            # Get full name of the attribute including the object name
            attr_full_name = "{}.{}".format(obj, attr)

            # Check if the attribute has any keys
            if mc.keyframe(attr_full_name, query=True, selected=True):
                # List all the keys of the attribute
                key_times = mc.keyframe(
                    attr_full_name, query=True, timeChange=True, selected=True
                )
                key_values = mc.keyframe(
                    attr_full_name, query=True, valueChange=True, selected=True
                )
                keys = list(zip(key_times, key_values))

                # Add keys to the corresponding attribute in the object dictionary
                object_dict[obj][attr] = keys

        # Add the object dictionary to the list if it has any keys
        if object_dict[obj]:
            selected_keys.append(object_dict)

    return selected_keys


def easeInOut(t, power):
    if t < 0.5:
        return (2 * t) ** power / 2
    else:
        return 1 - (-2 * t + 2) ** power / 2


def easeIn(t, power):
    return t**power


def easeOut(t, power):
    return 1 - (1 - t) ** power


def adjust_favoring(selected_objects, favor=1.0, midpoint=0.5):
    favor = favor * 10.0 + 1

    # Iterate over all objects and their attributes
    for object_dict in selected_objects:
        for obj, attr_dict in object_dict.items():
            for attr, keys in attr_dict.items():
                if len(keys) < 3:
                    print(
                        "For object {} and attribute {}, please select at least three keys to adjust favoring.".format(
                            obj, attr
                        )
                    )
                    continue

                # Get the first and last key
                first_key = keys[0]
                last_key = keys[-1]

                # Calculate the midpoint in value and time
                midValue = lerp(first_key[1], last_key[1], midpoint)
                midTime = lerp(first_key[0], last_key[0], midpoint)

                # Iterate over all keys (excluding the first and last key)
                for key in keys[1:-1]:
                    keyFavor = 1.0 - favor
                    func = easeInOut
                    if key[0] < midTime:
                        first_key_temp = keys[0]
                        last_key_temp = (midTime, midValue)
                        func = easeIn
                    else:
                        first_key_temp = (midTime, midValue)
                        last_key_temp = keys[-1]
                        func = easeOut

                    # Calculate the ratio
                    ratio = (key[0] - first_key_temp[0]) / (
                        last_key_temp[0] - first_key_temp[0]
                    )

                    # Adjust the ratio with the easeInOutQuint function
                    ratio = func(ratio, favor)

                    # Calculate the new value
                    new_value = lerp(first_key_temp[1], last_key_temp[1], ratio)

                    # Set the new key value
                    attr_full_name = "{}.{}".format(obj, attr)
                    mc.setKeyframe(attr_full_name, time=key[0], value=new_value)
                    mc.keyTangent(
                        attr_full_name,
                        time=(key[0],),
                        edit=True,
                        inTangentType="auto",
                        outTangentType="auto",
                    )

                mc.keyTangent(
                    attr_full_name,
                    time=(keys[0][0],),
                    edit=True,
                    inTangentType="auto",
                    outTangentType="auto",
                )
                mc.keyTangent(
                    attr_full_name,
                    time=(keys[-1][0],),
                    edit=True,
                    inTangentType="auto",
                    outTangentType="auto",
                )
            mc.dgdirty(obj)


def adjust_noise(selected_objects, amplitude=0, frequency=0.5):
    for object_dict in selected_objects:
        # add noise to each key value based on time multiplied by frequency and amplitude
        for obj, attr_dict in object_dict.items():
            for attr, keys in attr_dict.items():
                if len(keys) < 2:  # We need at least two keys to interpolate between
                    print(
                        "For object {} and attribute {}, please select at least two keys.".format(
                            obj, attr
                        )
                    )
                    continue

                # Iterate over all keys
                for key in keys:
                    new_value = (
                        key[1]
                        + noise.noise(
                            key[0] * frequency + keys[int(len(keys) / 2)][0] / 30.0,
                            keys[0][1],
                        )
                        * amplitude
                    )
                    # Set the new key value
                    attr_full_name = "{}.{}".format(obj, attr)
                    mc.setKeyframe(attr_full_name, time=key[0], value=new_value)

                mc.dgdirty(obj)


def adjust_spring(
    selected_objects, damp=0, frequency=0.5, useLastKeyAsDestination=False
):
    fps = get_fps()

    for object_dict in selected_objects:
        for obj, attr_dict in object_dict.items():
            for attr, keys in attr_dict.items():
                if len(keys) < 2:  # We need at least two keys to interpolate between
                    print(
                        "For object {} and attribute {}, please select at least two keys.".format(
                            obj, attr
                        )
                    )
                    continue

                # Iterate over all keys
                new_keys = copy.copy(keys)
                v = 0
                for i, key in enumerate(new_keys):
                    if i == 0:
                        continue

                    lastKeyDelta = key[0] - new_keys[i - 1][0]

                    new_value, v = MATH.spring(
                        new_keys[i - 1][1],
                        v,
                        new_keys[len(new_keys) - 1][1]
                        if useLastKeyAsDestination
                        else key[1],
                        damp,
                        frequency,
                        lastKeyDelta / fps,
                    )
                    new_keys[i] = (key[0], new_value)

                    # Set the new key value
                    attr_full_name = "{}.{}".format(obj, attr)
                    mc.setKeyframe(attr_full_name, time=key[0], value=new_value)

                mc.dgdirty(obj)


def adjust_offset(selected_objects, offset=0.0):
    for object_dict in selected_objects:
        for obj, attr_dict in object_dict.items():
            for attr, keys in attr_dict.items():
                if len(keys) < 2:  # We need at least two keys to interpolate between
                    print(
                        "For object {} and attribute {}, please select at least two keys.".format(
                            obj, attr
                        )
                    )
                    continue

                # unzip the time and values, offset the values by the offset amount, and zip them back together
                times, values = zip(*keys)
                values = deque(values)
                rotate_by = int(offset * len(values))
                values.rotate(rotate_by)
                new_keys = list(zip(times, values))

                # iterate through the keys and set the values
                for key in new_keys:
                    # Set the new key value
                    attr_full_name = "{}.{}".format(obj, attr)
                    mc.setKeyframe(attr_full_name, time=key[0], value=key[1])

                mc.dgdirty(obj)


def get_fps():
    time_unit = mc.currentUnit(q=True, time=True)
    fps = 0.0

    # Convert time unit to frames per second (FPS)
    if time_unit == "ntsc":
        fps = 30.0
    elif time_unit == "film":
        fps = 24.0
    elif time_unit == "pal":
        fps = 25.0
    elif time_unit == "show":
        fps = 48.0
    elif time_unit == "palf":
        fps = 50.0
    elif time_unit == "ntscf":
        fps = 60.0

    return fps
