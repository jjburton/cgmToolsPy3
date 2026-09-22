"""
simChain_dat
Josh Burton
www.cgmonastery.com

cgmDynSimTool preset + setup dat files — hair / hairShape / cloth / nucleus presets (Phase 1), setup re-wire (Phase 2).
"""
__MAYALOCAL = 'SIMCHAINDAT'

import copy
import os
import logging

import maya.cmds as mc

import cgm.core.cgm_Dat as CGMDAT
import cgm.core.cgm_General as cgmGEN
import cgm.core.cgmPy.validateArgs as VALID
import cgm.core.cgm_Meta as cgmMeta
import cgm.core.lib.nCloth_utils as NCLOTH
import cgm.core.rig.dynamic_utils as RIGDYN
import cgm.core.presets.cgmDynFK_presets as dynFKPresets
import cgm.core.presets.cgmNCloth_presets as nClothPresets

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DAT_EXTENSIONS = (
    'cgmSimHairDat', 'cgmSimHairShapeDat', 'cgmSimClothDat', 'cgmSimNucleusDat')
SETUP_EXTENSION = 'cgmSimChainSetup'
ALL_SIM_EXTENSIONS = DAT_EXTENSIONS + (SETUP_EXTENSION,)

_D_KIND_TO_CLASS = {}
_D_EXT_TO_CLASS = {}


def _empty_dat(datKind='', section='', profileKind='', differential=True):
    """Preset shell — no ``name`` (library identity is the filename). Setup dat keeps its own schema."""
    return {
        'schemaVersion': SCHEMA_VERSION,
        'datKind': datKind,
        'section': section,
        'profileKind': profileKind,
        'differential': differential,
        'profile': {},
    }


def _normalize_profile_keys(d):
    """JSON load may stringify ramp dict keys — restore int keys for Maya attrs."""
    if not isinstance(d, dict):
        return d
    out = {}
    for k, v in list(d.items()):
        nk = int(k) if isinstance(k, str) and k.isdigit() else k
        out[nk] = _normalize_profile_keys(v) if isinstance(v, dict) else v
    return out


def _dynfk_from_node(node):
    """Return cgmDynFK meta when node is a setup root."""
    mObj = cgmMeta.validateObjArg(node, noneValid=True)
    if mObj and getattr(mObj, 'mClass', None) == 'cgmDynFK':
        return mObj
    return None


def _ncloth_from_dynfk(mDynFK):
    """Resolve nClothShape from a cgmDynFK setup (mapped cloth message / get_dat fallbacks)."""
    if not mDynFK:
        return None

    mCloth = RIGDYN.get_mapped_cloth(mDynFK)
    if mCloth:
        _nc = NCLOTH.get_nCloth(mCloth.mNode, noneValid=True)
        if _nc:
            return _nc

    mCloth = mDynFK.getMessageAsMeta('mCloth')
    if mCloth:
        _nc = NCLOTH.get_nCloth(mCloth.mNode, noneValid=True)
        if _nc:
            return _nc

    if hasattr(mDynFK, 'get_dat'):
        _dat = mDynFK.get_dat() or {}
        mCloth = _dat.get('mCloth')
        if mCloth and mCloth is not False:
            _node = mCloth.mNode if hasattr(mCloth, 'mNode') else mCloth
            _nc = NCLOTH.get_nCloth(_node, noneValid=True)
            if _nc:
                return _nc
        mOut = _dat.get('mClothOutMesh')
        if mOut and mOut is not False:
            _node = mOut.mNode if hasattr(mOut, 'mNode') else mOut
            _nc = NCLOTH.get_nCloth(_node, noneValid=True)
            if _nc:
                return _nc
    return None


def _resolve_ncloth_for_capture(nodes=None, mDynFK=None):
    """Resolve nClothShape from loaded setup mapped cloth, selection, or cgmDynFK root."""
    if mDynFK:
        _nc = _ncloth_from_dynfk(mDynFK)
        if _nc:
            return _nc

    nodes = VALID.listArg(nodes) if nodes else (mc.ls(sl=True, long=True) or [])
    for n in nodes:
        mSetup = _dynfk_from_node(n)
        if mSetup:
            _nc = _ncloth_from_dynfk(mSetup)
            if _nc:
                return _nc
            continue
        _nc = NCLOTH.get_nCloth(n, noneValid=True)
        if _nc:
            return _nc
    return None


def _resolve_hairsystem_for_capture(nodes=None, mDynFK=None, mGrp=None):
    """Resolve hairSystem from selection, chain, setup default, or registry."""
    if mGrp and mDynFK:
        mHair = RIGDYN.hair_system_resolve_for_chain(mGrp, mDynFK)
        if mHair:
            return mHair.mNode

    nodes = VALID.listArg(nodes) if nodes else (mc.ls(sl=True, long=True) or [])
    for n in nodes:
        _hs = RIGDYN._resolve_hair_system_shape(n)
        if _hs:
            return _hs
        mSetup = _dynfk_from_node(n)
        if mSetup:
            mHair = RIGDYN.hair_system_get_default(mSetup)
            if mHair:
                return mHair.mNode
            ml_reg = RIGDYN.hair_system_list_registered(mSetup)
            if ml_reg:
                return ml_reg[0].mNode
        mObj = cgmMeta.validateObjArg(n, noneValid=True)
        if mObj and getattr(mObj, 'mClass', None) == 'cgmDynFK':
            mHair = RIGDYN.hair_system_get_default(mObj)
            if mHair:
                return mHair.mNode

    if mDynFK:
        mHair = RIGDYN.hair_system_get_default(mDynFK)
        if mHair:
            return mHair.mNode
    return None


def _resolve_nucleus_for_capture(nodes=None, mDynFK=None):
    """Resolve nucleus from loaded setup, selection, nCloth, or cgmDynFK root."""
    if mDynFK:
        mNuc = mDynFK.getMessageAsMeta('mNucleus')
        if mNuc:
            return mNuc.mNode

    nodes = VALID.listArg(nodes) if nodes else (mc.ls(sl=True, long=True) or [])
    for n in nodes:
        if mc.objectType(n) == 'nucleus':
            return n
        _nc = NCLOTH.get_nCloth(n, noneValid=True)
        if _nc:
            _nucleus = NCLOTH.get_nucleus(_nc, noneValid=True)
            if _nucleus:
                return _nucleus
        mSetup = _dynfk_from_node(n)
        if mSetup:
            mNuc = mSetup.getMessageAsMeta('mNucleus')
            if mNuc:
                return mNuc.mNode
    return None


class SimPresetDatBase(CGMDAT.data):
    _dataFormat = 'json'
    datKind = ''
    section = ''
    defaultProfileKind = ''

    def __init__(self, filepath=None, dat=None, **kws):
        kws.setdefault('dataFormat', self._dataFormat)
        super().__init__(filepath, **kws)
        self.structureMode = 'dev'
        if dat:
            self.dat = dat
        elif not self.dat:
            self.dat = _empty_dat(
                datKind=self.datKind,
                section=self.section,
                profileKind=self.defaultProfileKind,
            )

    def read(self, filepath=None, decode=True, report=False, startDirMode=None):
        _result = super().read(filepath, decode=decode, report=report, startDirMode=startDirMode)
        if _result and self.dat:
            # Legacy files may still carry meta / name — ignore; do not re-persist
            self.dat.pop('meta', None)
            self.dat.pop('name', None)
            if self.dat.get('profile'):
                self.dat['profile'] = _normalize_profile_keys(self.dat['profile'])
        return _result

    def _preset_log_label(self):
        """Filename stem when available; else datKind."""
        _fp = getattr(self, 'str_filepath', None) or ''
        if _fp:
            return os.path.splitext(os.path.basename(_fp))[0]
        return self.datKind or 'preset'

    def _build_dat(self, profile, differential=True, profileKind=None, name=None,
                   **_unused):
        """Build preset dat. ``name`` / ``sourceNode`` ignored (legacy; not stored)."""
        self.dat = _empty_dat(
            datKind=self.datKind,
            section=self.section,
            profileKind=profileKind or self.defaultProfileKind,
            differential=differential,
        )
        self.dat['profile'] = copy.deepcopy(profile or {})
        return self.dat

    def write(self, filepath=None, update=False, startDirMode=None, forcePrompt=False):
        if isinstance(self.dat, dict):
            self.dat.pop('meta', None)
            self.dat.pop('name', None)
        return super().write(
            filepath=filepath, update=update,
            startDirMode=startDirMode, forcePrompt=forcePrompt)

    def capture(self, nodes=None, differential=True, name=None, profileKind=None):
        _str_func = 'SimPresetDatBase.capture'
        raise NotImplementedError(cgmGEN.logString_msg(_str_func, 'Subclass must implement'))

    def apply(self, target=None, clean=True, mDynFK=None, mGrp=None):
        _str_func = '{0}.apply'.format(self.__class__.__name__)
        profile = self.dat.get('profile') or {}
        if not profile:
            return log.warning(cgmGEN.logString_msg(_str_func, 'Empty profile'))

        _profileKind = self.dat.get('profileKind') or self.defaultProfileKind
        _section = self.dat.get('section') or self.section

        _target = self._resolve_apply_target(target, mDynFK=mDynFK, mGrp=mGrp)
        if not _target:
            return log.warning(cgmGEN.logString_msg(
                _str_func, 'No apply target for {0}'.format(self.datKind)))

        if _section == 'hs':
            return RIGDYN.profile_apply_section(
                _target, profile, section='hs', clean=clean, profileKind=_profileKind)
        return NCLOTH.profile_apply_section(
            _target, profile, section=self.section, clean=clean,
            profileKind=_profileKind, module=nClothPresets)

    def _resolve_apply_target(self, target=None, mDynFK=None, mGrp=None):
        raise NotImplementedError

    @classmethod
    def from_module_profile(cls, profileName, module=None, differential=True):
        """Build dat dict from shipped Python preset module entry."""
        profileName = profileName or ''
        if cls.datKind == 'hair':
            module = module or dynFKPresets
            _d = RIGDYN.profile_get(profileName, module)
            if not _d or not _d.get('hs'):
                return None
            _profile = copy.deepcopy(_d['hs'])
            _profileKind = RIGDYN.profile_kind(profileName, module) or 'hair'
            if differential:
                _wrapped = NCLOTH.profile_diff_from_base({'hs': _profile}, module=module)
                _profile = _wrapped.get('hs') or {}
        elif cls.datKind == 'cloth':
            module = module or nClothPresets
            _d = NCLOTH.profile_get(profileName, module)
            if not _d or not _d.get('nc'):
                return None
            _profile = copy.deepcopy(_d['nc'])
            _profileKind = NCLOTH.profile_kind(profileName, module) or 'fabric'
            if differential:
                _wrapped = NCLOTH.profile_diff_from_base({'nc': _profile}, module=module)
                _profile = _wrapped.get('nc') or {}
        else:
            module = module or nClothPresets
            _d = NCLOTH.profile_get(profileName, module)
            if not _d or not _d.get('n'):
                return None
            _profile = copy.deepcopy(_d['n'])
            _profileKind = NCLOTH.profile_kind(profileName, module) or 'solver'
            if differential:
                _wrapped = NCLOTH.profile_diff_from_base({'n': _profile}, module=module)
                _profile = _wrapped.get('n') or {}

        inst = cls()
        inst._build_dat(
            _profile,
            differential=differential,
            profileKind=_profileKind,
        )
        return inst.dat


class SimHairDat(SimPresetDatBase):
    _ext = 'cgmSimHairDat'
    _startDir = ['cgmDat', 'sim', 'hair']
    datKind = 'hair'
    section = 'hs'
    defaultProfileKind = 'hair'

    def capture(self, nodes=None, differential=True, name=None, profileKind=None, mDynFK=None):
        _str_func = 'SimHairDat.capture'
        _node = _resolve_hairsystem_for_capture(nodes=nodes, mDynFK=mDynFK)

        if not _node:
            log.warning(cgmGEN.logString_msg(
                _str_func, 'Select hairSystem or load cgmDynFK with hair mapped'))
            return None

        _prof = RIGDYN.get_dat(_node, differential=differential, hs_profile_scope='dynamic')
        _profile = {}
        if isinstance(_prof, dict):
            _profile = _prof.get('hs') or _prof.get('hairSystem') or {}
            if not _profile and len(_prof) == 1:
                _profile = list(_prof.values())[0]

        return self._build_dat(
            _profile,
            differential=differential,
            profileKind=profileKind or 'hair',
        )

    def apply(self, target=None, clean=True, mDynFK=None, mGrp=None):
        _str_func = 'SimHairDat.apply'
        profile = copy.deepcopy(self.dat.get('profile') or {})
        if not profile:
            return log.warning(cgmGEN.logString_msg(_str_func, 'Empty profile'))

        _label = self._preset_log_label()
        _section = self.dat.get('section') or self.section
        _profileKind = self.dat.get('profileKind') or self.defaultProfileKind

        if _section == 'hairShape' or _profileKind == 'hairShape':
            return log.warning(cgmGEN.logString_msg(
                _str_func,
                "'{0}' is a legacy HairShape preset on a hair dat — not applied. "
                "Re-save shape as .cgmSimHairShapeDat and dynamic feel as .cgmSimHairDat.".format(
                    _label)))

        _dynamic, _removed = RIGDYN.hair_profile_filter_feel(profile)
        if _removed:
            log.warning(cgmGEN.logString_msg(
                _str_func,
                "'{0}' dropped non-feel attrs ({1}) — collide/shape/solver keys are not hair feel. "
                "Re-save with Save Hair Dat… for a clean differential.".format(
                    _label, ', '.join(sorted(_removed)))))

        if not _dynamic:
            if _removed:
                return log.warning(cgmGEN.logString_msg(
                    _str_func,
                    "'{0}' has no hair-feel attrs after filter.".format(_label)))
            return log.warning(cgmGEN.logString_msg(_str_func, 'Empty profile'))

        _target = self._resolve_apply_target(target, mDynFK=mDynFK, mGrp=mGrp)
        if not _target:
            return log.warning(cgmGEN.logString_msg(
                _str_func, 'No apply target for hair dat'))

        return RIGDYN.profile_apply_section(
            _target, _dynamic, section='hs', clean=clean, profileKind='hair')

    def _resolve_apply_target(self, target=None, mDynFK=None, mGrp=None):
        if target:
            _hs = RIGDYN._resolve_hair_system_shape(target)
            return _hs or VALID.mNodeString(target)
        if mGrp and mDynFK:
            mHair = RIGDYN.hair_system_resolve_for_chain(mGrp, mDynFK)
            if mHair:
                return mHair.mNode
        if mDynFK:
            mHair = RIGDYN.hair_system_get_default(mDynFK)
            if mHair:
                return mHair.mNode
        nodes = mc.ls(sl=True, long=True) or []
        for n in nodes:
            _hs = RIGDYN._resolve_hair_system_shape(n)
            if _hs:
                return _hs
        return None


class SimHairShapeDat(SimPresetDatBase):
    _ext = 'cgmSimHairShapeDat'
    _startDir = ['cgmDat', 'sim', 'hairShape']
    datKind = 'hairShape'
    section = 'hs'
    defaultProfileKind = 'hairShape'

    def capture(self, nodes=None, differential=True, name=None, profileKind=None,
                mDynFK=None, mGrp=None):
        _str_func = 'SimHairShapeDat.capture'
        mGrp = cgmMeta.validateObjArg(mGrp, noneValid=True)
        if mGrp:
            _profile = RIGDYN.get_hair_shape_profile(mGrp, mDynFK, differential=differential)
            return self._build_dat(
                _profile,
                differential=differential,
                profileKind=profileKind or 'hairShape',
            )

        _node = _resolve_hairsystem_for_capture(nodes=nodes, mDynFK=mDynFK)
        if not _node:
            log.warning(cgmGEN.logString_msg(
                _str_func, 'Select hairSystem, chain grp, or loaded cgmDynFK with hair'))
            return None

        _profile = RIGDYN.get_hair_system_shape_profile(_node, differential=differential)
        return self._build_dat(
            _profile,
            differential=differential,
            profileKind=profileKind or 'hairShape',
        )

    def apply(self, target=None, clean=True, mDynFK=None, mGrp=None):
        _str_func = '{0}.apply'.format(self.__class__.__name__)
        profile = self.dat.get('profile') or {}
        if not profile:
            return log.warning(cgmGEN.logString_msg(_str_func, 'Empty profile'))

        mGrp = cgmMeta.validateObjArg(mGrp, noneValid=True)
        if mGrp:
            return RIGDYN.apply_hair_shape_profile(mGrp, mDynFK, profile, clean=clean)

        _target = self._resolve_apply_target(target, mDynFK=mDynFK, mGrp=mGrp)
        if not _target:
            return log.warning(cgmGEN.logString_msg(
                _str_func, 'No hairSystem apply target'))
        return RIGDYN.apply_hair_system_shape_profile(_target, profile, clean=clean)

    def _resolve_apply_target(self, target=None, mDynFK=None, mGrp=None):
        if target:
            _hs = RIGDYN._resolve_hair_system_shape(target)
            return _hs or VALID.mNodeString(target)
        if mGrp and mDynFK:
            mHair = RIGDYN.hair_system_resolve_for_chain(mGrp, mDynFK)
            if mHair:
                return mHair.mNode
        if mDynFK:
            mHair = RIGDYN.hair_system_get_default(mDynFK)
            if mHair:
                return mHair.mNode
        nodes = mc.ls(sl=True, long=True) or []
        for n in nodes:
            _hs = RIGDYN._resolve_hair_system_shape(n)
            if _hs:
                return _hs
        return None


class SimClothDat(SimPresetDatBase):
    _ext = 'cgmSimClothDat'
    _startDir = ['cgmDat', 'sim', 'cloth']
    datKind = 'cloth'
    section = 'nc'
    defaultProfileKind = 'fabric'

    def capture(self, nodes=None, differential=True, name=None, profileKind=None, mDynFK=None):
        _str_func = 'SimClothDat.capture'
        _nc = _resolve_ncloth_for_capture(nodes=nodes, mDynFK=mDynFK)

        if not _nc:
            log.warning(cgmGEN.logString_msg(
                _str_func, 'Select nCloth or map cloth on loaded cgmDynFK setup'))
            return None

        _dat = NCLOTH.query_settings(_nc, differential=differential)
        _profile = (_dat.get('profile') or {}).get('nc') or {}
        return self._build_dat(
            _profile,
            differential=differential,
            profileKind=profileKind or 'fabric',
        )

    def apply(self, target=None, clean=True, mDynFK=None, mGrp=None):
        """Apply fabric feel to nCloth only — never writes nucleus."""
        _str_func = 'SimClothDat.apply'
        profile = self.dat.get('profile') or {}
        if not profile:
            return log.warning(cgmGEN.logString_msg(_str_func, 'Empty profile'))

        _target = self._resolve_apply_target(target, mDynFK=mDynFK, mGrp=mGrp)
        if not _target:
            return log.warning(cgmGEN.logString_msg(
                _str_func, 'No apply target for cloth'))

        return NCLOTH.profile_apply_section(
            _target, profile, section='nc', clean=clean,
            profileKind='fabric', module=nClothPresets)

    def _resolve_apply_target(self, target=None, mDynFK=None, mGrp=None):
        if target:
            _nc = NCLOTH.get_nCloth(target, noneValid=True)
            return _nc or VALID.mNodeString(target)
        if mDynFK:
            mCloth = RIGDYN.get_mapped_cloth(mDynFK)
            if mCloth:
                _nc = NCLOTH.get_nCloth(mCloth.mNode, noneValid=True)
                if _nc:
                    return _nc
        nodes = mc.ls(sl=True, long=True) or []
        for n in nodes:
            _nc = NCLOTH.get_nCloth(n, noneValid=True)
            if _nc:
                return _nc
        return None


class SimNucleusDat(SimPresetDatBase):
    _ext = 'cgmSimNucleusDat'
    _startDir = ['cgmDat', 'sim', 'nucleus']
    datKind = 'nucleus'
    section = 'n'
    defaultProfileKind = 'solver'

    def capture(self, nodes=None, differential=True, name=None, profileKind=None, mDynFK=None):
        _str_func = 'SimNucleusDat.capture'
        _nucleus = _resolve_nucleus_for_capture(nodes=nodes, mDynFK=mDynFK)

        if not _nucleus:
            log.warning(cgmGEN.logString_msg(
                _str_func, 'Select nucleus/nCloth or load cgmDynFK with nucleus mapped'))
            return None

        _dat = NCLOTH.query_nucleus_settings(_nucleus, differential=differential)
        _profile = (_dat.get('profile') or {}).get('n') or {}
        _kind = profileKind
        if not _kind:
            _kind = 'solver'
        return self._build_dat(
            _profile,
            differential=differential,
            profileKind=_kind,
        )

    def apply(self, target=None, clean=True, mDynFK=None, mGrp=None):
        """Apply nucleus layer only — never seeds full base.n or writes nCloth."""
        _str_func = 'SimNucleusDat.apply'
        profile = self.dat.get('profile') or {}
        if not profile:
            return log.warning(cgmGEN.logString_msg(_str_func, 'Empty profile'))

        _target = self._resolve_apply_target(target, mDynFK=mDynFK, mGrp=mGrp)
        if not _target:
            return log.warning(cgmGEN.logString_msg(
                _str_func, 'No apply target for nucleus'))

        _kind = self.dat.get('profileKind') or self.defaultProfileKind
        # Library nucleus dats are solver/wind layers — never utility/base (would dump base.n)
        if _kind not in ('solver', 'wind'):
            log.warning(cgmGEN.logString_msg(
                _str_func,
                "Nucleus dat profileKind {0!r} coerced to 'solver' (overlay only)".format(_kind)))
            _kind = 'solver'

        return NCLOTH.profile_apply_section(
            _target, profile, section='n', clean=clean,
            profileKind=_kind, module=nClothPresets)

    def _resolve_apply_target(self, target=None, mDynFK=None, mGrp=None):
        if target:
            if mc.objectType(target) == 'nucleus':
                return VALID.mNodeString(target)
            _nc = NCLOTH.get_nCloth(target, noneValid=True)
            if _nc:
                return NCLOTH.get_nucleus(_nc, noneValid=True)
            return VALID.mNodeString(target)
        if mDynFK:
            mNuc = mDynFK.getMessageAsMeta('mNucleus')
            if mNuc:
                return mNuc.mNode
        nuclei = NCLOTH._resolve_nuclei(None)
        return nuclei[0] if nuclei else None


def _node_ref(node):
    """Serialize a Maya node or meta instance to a long-name string."""
    if not node:
        return ''
    if hasattr(node, 'mNode'):
        return VALID.mNodeString(node.mNode)
    return VALID.mNodeString(node)


def _resolve_node_ref(ref, typeFilter=None):
    """Resolve a stored node reference to a scene long name."""
    _str_func = '_resolve_node_ref'
    if not ref:
        return None
    ref = VALID.stringArg(ref, noneValid=True)
    if not ref:
        return None
    if mc.objExists(ref):
        _node = VALID.mNodeString(ref)
        if typeFilter and not mc.objectType(_node, isType=typeFilter):
            return None
        return _node

    _short = ref.split('|')[-1].split(':')[-1]
    _candidates = mc.ls(_short, long=True) or []
    if typeFilter:
        _filtered = [n for n in _candidates if mc.objectType(n, isType=typeFilter)]
        _candidates = _filtered or _candidates

    if len(_candidates) == 1:
        return _candidates[0]
    if len(_candidates) > 1:
        log.warning(cgmGEN.logString_msg(_str_func, 'Ambiguous ref: {0}'.format(ref)))
    return None


def _find_dynfk_setup(baseName=None, setupRoot=None):
    """Find an existing cgmDynFK setup in the scene."""
    if setupRoot:
        _node = _resolve_node_ref(setupRoot)
        if _node:
            mObj = cgmMeta.validateObjArg(_node, noneValid=True)
            if mObj and getattr(mObj, 'mClass', None) == 'cgmDynFK':
                return mObj

    if baseName:
        _guess = '{0}_dynFK'.format(baseName)
        if mc.objExists(_guess):
            mObj = cgmMeta.validateObjArg(_guess, noneValid=True)
            if mObj and getattr(mObj, 'mClass', None) == 'cgmDynFK':
                return mObj

    for n in mc.ls(type='transform') or []:
        mObj = cgmMeta.validateObjArg(n, noneValid=True)
        if mObj and getattr(mObj, 'mClass', None) == 'cgmDynFK':
            if not baseName or getattr(mObj, 'baseName', None) == baseName or mObj.cgmName == baseName:
                return mObj
    return None


def resolve_library_filepath(key, mode='dev', modes=None, extensions=None):
    """Resolve library key (hair.bob or hair/bob) to an on-disk dat path."""
    if not key:
        return None
    key = key.replace('/', '.')
    if extensions is None:
        extensions = list(DAT_EXTENSIONS)
    if modes is None and isinstance(mode, (list, tuple)):
        modes = mode
    if modes is not None:
        _rows = get_library_rows(modes=modes, force=True)
        for r in _rows:
            if r.get('key') == key:
                return r.get('filepath')
        for r in _rows:
            k = r.get('key') or ''
            if k.endswith('.{0}'.format(key)) or k.split('.')[-1] == key.split('.')[-1]:
                return r.get('filepath')
        return None
    _options, _ = get_library_options(force=True, mode=mode, extensions=extensions)
    if key in _options:
        return _options[key]
    for k, v in list(_options.items()):
        if k.endswith('.{0}'.format(key)) or k.split('.')[-1] == key.split('.')[-1]:
            return v
    return None

def apply_preset_ref(ref, mDynFK=None, mode='dev', clean=True):
    """Load and apply a preset dat from a library key."""
    _path = resolve_library_filepath(ref, mode=mode, extensions=list(DAT_EXTENSIONS))
    if not _path or not os.path.isfile(_path):
        log.warning('Preset ref not found: {0}'.format(ref))
        return False
    inst, _dat = read_dat(_path)
    if not inst:
        return False
    inst.apply(mDynFK=mDynFK, clean=clean)
    return True


class SimChainSetup(CGMDAT.data):
    """Full cgmDynFK setup recipe — map nodes + rebuild chains when scene elements exist."""

    _ext = SETUP_EXTENSION
    _dataFormat = 'json'
    _startDir = ['cgmDat', 'sim', 'setups']

    def __init__(self, filepath=None, dat=None, **kws):
        kws.setdefault('dataFormat', self._dataFormat)
        super().__init__(filepath, **kws)
        self.structureMode = 'dev'
        if dat:
            self.dat = dat
        elif not self.dat:
            self.dat = self._empty_setup_dat()

    def read(self, filepath=None, decode=True, report=False, startDirMode=None):
        _result = super().read(filepath, decode=decode, report=report, startDirMode=startDirMode)
        if _result and isinstance(self.dat, dict):
            self.dat.pop('meta', None)
        return _result

    def write(self, filepath=None, update=False, startDirMode=None, forcePrompt=False):
        if isinstance(self.dat, dict):
            self.dat.pop('meta', None)
        return super().write(
            filepath=filepath, update=update,
            startDirMode=startDirMode, forcePrompt=forcePrompt)

    @staticmethod
    def _empty_setup_dat(name='setup'):
        return {
            'schemaVersion': SCHEMA_VERSION,
            'name': name,
            'baseName': name,
            'setupRoot': '',
            'options': {
                'fwd': 'z+',
                'up': 'y+',
                'startFrame': -50,
                'upSetup': 'guess',
                'extendStart': None,
                'addEndJoint': False,
                'extendEnd': False,
                'advancedTwist': False,
                'aimUpMode': 'joint',
                'fixedSegmentLength': False,
                'follicleSegmentLength': 1.0,
                'follicleSampleDensity': 1.0,
            },
            'mapped': {},
            'chains': [],
            'presetRefs': {},
        }

    def capture(self, mDynFK=None, name=None):
        _str_func = 'SimChainSetup.capture'
        mSetup = cgmMeta.validateObjArg(mDynFK, noneValid=True)
        if not mSetup:
            nodes = mc.ls(sl=True, long=True) or []
            for n in nodes:
                mSetup = cgmMeta.validateObjArg(n, noneValid=True)
                if mSetup and getattr(mSetup, 'mClass', None) == 'cgmDynFK':
                    break
        if not mSetup or getattr(mSetup, 'mClass', None) != 'cgmDynFK':
            log.warning(cgmGEN.logString_msg(_str_func, 'Select or pass a cgmDynFK setup'))
            return None

        _runtime = mSetup.get_dat() or {}
        _base = mSetup.baseName or mSetup.cgmName or mSetup.p_nameBase.replace('_dynFK', '')
        _name = name or _base

        self.dat = self._empty_setup_dat(_name)
        self.dat['baseName'] = _base
        self.dat['setupRoot'] = _node_ref(mSetup)
        self.dat['options'] = {
            'fwd': mSetup.fwd or 'z+',
            'up': mSetup.up or 'y+',
            'startFrame': mSetup.startFrame,
            'upSetup': mSetup.upSetup or 'guess',
            'extendStart': mSetup.extendStart,
            'addEndJoint': getattr(mSetup, 'addEndJoint', False),
            'extendEnd': getattr(mSetup, 'extendEnd', False),
            'advancedTwist': getattr(mSetup, 'advancedTwist', False),
            'aimUpMode': mSetup.aimUpMode or 'joint',
            'fixedSegmentLength': getattr(mSetup, 'fixedSegmentLength', False),
            'follicleSegmentLength': getattr(mSetup, 'follicleSegmentLength', 1.0),
            'follicleSampleDensity': getattr(mSetup, 'follicleSampleDensity', 1.0),
        }

        _mapped = {}
        if _runtime.get('mNucleus'):
            _mapped['nucleus'] = _node_ref(_runtime['mNucleus'])
        if _runtime.get('mCloth'):
            _mapped['cloth'] = _node_ref(_runtime['mCloth'])
        if _runtime.get('mHairSysShape'):
            _mapped['hairSystem'] = _node_ref(_runtime['mHairSysShape'])
        _ml_hs = _runtime.get('mHairSystems') or []
        if _ml_hs:
            _mapped['hairSystems'] = [_node_ref(h) for h in _ml_hs if h]
        if _runtime.get('mClothOutMesh'):
            _mapped['clothOutMesh'] = _node_ref(_runtime['mClothOutMesh'])
        self.dat['mapped'] = _mapped

        _chains = []
        for idx in sorted(_runtime.get('chains', {}).keys()):
            _d = _runtime['chains'][idx]
            mGrp = _d.get('mGrp')
            if not mGrp:
                continue
            _entry = {
                'index': idx,
                'name': getattr(mGrp, 'cgmName', None) or 'chain_{0}'.format(idx),
                'chainMode': _d.get('chainMode') or 'hair',
                'targets': [_node_ref(t) for t in (_d.get('mTargets') or []) if t],
            }
            if _entry['chainMode'] == 'clothAttach':
                _entry['surfaceTrack'] = _d.get('surfaceTrack') or 'follicle'
            if _entry['chainMode'] == 'hair':
                _mhs = _d.get('mHairSysShape')
                if _mhs:
                    _entry['hairSystem'] = _node_ref(_mhs)
                _entry['options'] = {
                    'fwd': getattr(mGrp, 'fwd', None) or mSetup.fwd,
                    'up': getattr(mGrp, 'up', None) or mSetup.up,
                    'upSetup': mSetup.upSetup,
                    'extendStart': mSetup.extendStart,
                    'addEndJoint': RIGDYN._hair_add_end_joint_from_grp(mGrp),
                    'extendEnd': RIGDYN._hair_curve_extend_end_from_grp(mGrp),
                    'aimUpMode': mSetup.aimUpMode,
                    'fixedSegmentLength': getattr(mGrp, 'fixedSegmentLength', getattr(mSetup, 'fixedSegmentLength', False)),
                    'follicleSegmentLength': getattr(
                        mGrp, 'follicleSegmentLength', getattr(mSetup, 'follicleSegmentLength', 1.0)),
                    'follicleSampleDensity': getattr(
                        mGrp, 'follicleSampleDensity', getattr(mSetup, 'follicleSampleDensity', 1.0)),
                    'hairFollowMode': RIGDYN._get_chain_hair_follow_mode(mGrp),
                    'inCurveDegree': int(getattr(mGrp, 'inCurveDegree', getattr(mSetup, 'inCurveDegree', 1))),
                    'outCurveDegree': int(getattr(mGrp, 'outCurveDegree', getattr(mSetup, 'outCurveDegree', 2))),
                    'advancedTwist': RIGDYN._hair_advanced_twist_from_grp(mGrp),
                }
            _chains.append(_entry)

        self.dat['chains'] = _chains
        self.dat.pop('meta', None)
        log.info(cgmGEN.logString_msg(
            _str_func, '{0} | chains: {1}'.format(_name, len(_chains))))
        return self.dat

    def apply(self, mDynFK=None, recreateChains=True, applyPresets=True, mode='dev'):
        """
        Re-wire a cgmDynFK setup from dat when mapped nodes and targets exist in the scene.

        :returns: cgmDynFK meta instance or None
        """
        _str_func = 'SimChainSetup.apply'
        _dat = self.dat or {}
        _base = _dat.get('baseName') or _dat.get('name') or 'DynamicChain'
        _opts = _dat.get('options') or {}

        mSetup = cgmMeta.validateObjArg(mDynFK, noneValid=True)
        if mSetup and getattr(mSetup, 'mClass', None) != 'cgmDynFK':
            mSetup = None
        if not mSetup:
            mSetup = _find_dynfk_setup(_base, _dat.get('setupRoot'))

        if not mSetup:
            mSetup = RIGDYN.setup_sim_dynFK(
                baseName=_base,
                startFrame=_opts.get('startFrame'),
                applyPreset=False,
            )
            log.info(cgmGEN.logString_msg(_str_func, 'Created setup: {0}'.format(mSetup.p_nameBase)))

        if _base and mSetup.baseName != _base:
            mSetup.set_base_name(_base)

        _mapped = _dat.get('mapped') or {}
        _nuc = _resolve_node_ref(_mapped.get('nucleus'), typeFilter='nucleus')
        if _nuc:
            RIGDYN.map_nucleus(mSetup, _nuc)
        _cloth = _resolve_node_ref(_mapped.get('cloth'))
        if _cloth:
            RIGDYN.map_cloth_surface(mSetup, _cloth)
        _hair = _resolve_node_ref(_mapped.get('hairSystem'), typeFilter='hairSystem')
        if _hair:
            RIGDYN.map_hair_system(mSetup, _hair)
        for _href in _mapped.get('hairSystems') or []:
            _hn = _resolve_node_ref(_href, typeFilter='hairSystem')
            if _hn:
                RIGDYN.hair_system_register(mSetup, _hn, setDefault=False)

        for _chainDat in _dat.get('chains') or []:
            self._apply_chain(mSetup, _chainDat, recreateChains=recreateChains)

        if applyPresets:
            _refs = copy.deepcopy(_dat.get('presetRefs') or {})
            for _chainDat in _dat.get('chains') or []:
                for k, v in (_chainDat.get('presetRefs') or {}).items():
                    _refs.setdefault(k, v)
            for _kind in ('nucleus', 'cloth', 'hair'):
                if _refs.get(_kind):
                    apply_preset_ref(_refs[_kind], mDynFK=mSetup, mode=mode)

        log.info(cgmGEN.logString_msg(_str_func, 'Setup applied: {0}'.format(mSetup.p_nameBase)))
        return mSetup

    def _apply_chain(self, mSetup, chainDat, recreateChains=True):
        _str_func = 'SimChainSetup._apply_chain'
        _targets = []
        for ref in chainDat.get('targets') or []:
            _node = _resolve_node_ref(ref)
            if not _node:
                log.warning(cgmGEN.logString_msg(
                    _str_func, 'Missing target: {0}'.format(ref)))
                return False
            _targets.append(_node)

        if not _targets:
            return False

        ml_targets = cgmMeta.asMeta(_targets, noneValid=True)
        if not ml_targets:
            return False

        _mode = chainDat.get('chainMode') or 'hair'
        _name = chainDat.get('name') or ml_targets[-1].p_nameBase
        _idx = chainDat.get('index')

        if not recreateChains and _idx is not None:
            ml_chains = mSetup.msgList_get('chain') or []
            if _idx < len(ml_chains):
                mGrp = ml_chains[_idx]
                if self._chain_matches(mGrp, chainDat):
                    log.info(cgmGEN.logString_msg(
                        _str_func, 'Chain {0} verified — skip recreate'.format(_idx)))
                    return True

        if _idx is not None:
            try:
                mSetup.chain_deleteByIdx(_idx)
            except Exception:
                pass

        if _mode == 'clothAttach':
            RIGDYN.attach_to_cloth_dynFK(
                mSetup,
                objs=ml_targets,
                name=_name,
                surfaceTrack=chainDat.get('surfaceTrack') or 'follicle',
            )
        else:
            _copts = chainDat.get('options') or {}
            _setupOpts = self.dat.get('options') or {}
            _hair_mode = 'default'
            _hair_ref = chainDat.get('hairSystem')
            if _hair_ref:
                _hn = _resolve_node_ref(_hair_ref, typeFilter='hairSystem')
                if _hn and mc.objExists(_hn):
                    RIGDYN.hair_system_register(mSetup, _hn, setDefault=False)
                    _hair_mode = cgmMeta.asMeta(_hn).p_nameBase
                else:
                    _hair_mode = 'new'
            mSetup.chain_create_hair(
                objs=ml_targets,
                name=_name,
                hairSystemMode=_hair_mode,
                fwd=_copts.get('fwd') or _setupOpts.get('fwd'),
                up=_copts.get('up') or _setupOpts.get('up'),
                upSetup=_copts.get('upSetup') or _setupOpts.get('upSetup'),
                extendStart=_copts.get('extendStart', _setupOpts.get('extendStart')),
                addEndJoint=_copts.get('addEndJoint', _setupOpts.get('addEndJoint')),
                extendEnd=_copts.get('extendEnd', _setupOpts.get('extendEnd')),
                aimUpMode=_copts.get('aimUpMode') or _setupOpts.get('aimUpMode'),
                fixedSegmentLength=_copts.get(
                    'fixedSegmentLength', _setupOpts.get('fixedSegmentLength', False)),
                follicleSegmentLength=_copts.get(
                    'follicleSegmentLength', _setupOpts.get('follicleSegmentLength', 1.0)),
                follicleSampleDensity=_copts.get(
                    'follicleSampleDensity', _setupOpts.get('follicleSampleDensity', 1.0)),
                hairFollowMode=_copts.get('hairFollowMode', _setupOpts.get('hairFollowMode')),
                inCurveDegree=_copts.get('inCurveDegree', _setupOpts.get('inCurveDegree', 1)),
                outCurveDegree=_copts.get('outCurveDegree', _setupOpts.get('outCurveDegree', 2)),
                advancedTwist=_copts.get('advancedTwist', _setupOpts.get('advancedTwist', False)),
            )
        return True

    @staticmethod
    def _chain_matches(mGrp, chainDat):
        if not mGrp:
            return False
        _mode = getattr(mGrp, 'chainMode', None) or 'hair'
        if _mode != (chainDat.get('chainMode') or 'hair'):
            return False
        if _mode == 'clothAttach':
            _track = getattr(mGrp, 'surfaceTrack', None) or 'follicle'
            if _track != (chainDat.get('surfaceTrack') or 'follicle'):
                return False
        ml = mGrp.msgList_get('mTargets') or []
        _existing = sorted([_node_ref(t) for t in ml if t])
        _expected = sorted(chainDat.get('targets') or [])
        return _existing == _expected


def _register_classes():
    global _D_KIND_TO_CLASS, _D_EXT_TO_CLASS
    for cls in (SimHairDat, SimHairShapeDat, SimClothDat, SimNucleusDat):
        _D_KIND_TO_CLASS[cls.datKind] = cls
        _D_EXT_TO_CLASS[cls._ext] = cls
    _D_EXT_TO_CLASS[SimChainSetup._ext] = SimChainSetup


_register_classes()


def dat_class_for_kind(kind):
    return _D_KIND_TO_CLASS.get(kind)


def dat_class_for_ext(ext):
    return _D_EXT_TO_CLASS.get(ext)


def dat_class_for_filepath(filepath):
    if not filepath:
        return None
    _base = os.path.basename(filepath)
    if '.' not in _base:
        return None
    _ext = _base.rsplit('.', 1)[-1]
    return dat_class_for_ext(_ext)


def read_dat(filepath):
    """Read any sim dat file; returns (instance, dat dict)."""
    cls = dat_class_for_filepath(filepath)
    if not cls:
        log.warning('Unknown sim dat extension: {0}'.format(filepath))
        return None, None
    inst = cls(filepath=filepath)
    if inst.read(filepath):
        return inst, inst.dat
    return None, None


def read_any_dat(filepath):
    """Alias for read_dat — preset or setup file."""
    return read_dat(filepath)


def get_library_path(mode='dev'):
    base = CGMDAT.startDir_getBase(mode)
    return os.path.join(base, 'cgmDat', 'sim')


def get_setups_library_path(mode='dev'):
    base = CGMDAT.startDir_getBase(mode)
    return os.path.join(base, 'cgmDat', 'sim', 'setups')


def get_library_options(force=False, path=None, mode='dev', modes=None, extensions=None):
    """
    Scan cgmDat/sim for shipped preset and/or setup files.

    mode: single root (legacy). modes: list of roots for collective scan.
    When modes is set (or mode is a list), returns (rows, by_mode) where rows
    are CGMDAT.library_options_merge entries. Otherwise returns (options, types).
    """
    if extensions is None:
        extensions = list(DAT_EXTENSIONS)
    if modes is None and isinstance(mode, (list, tuple)):
        modes = mode
    if modes is not None:
        return CGMDAT.get_ext_options_multi(
            modes=modes, path_join=['cgmDat', 'sim'],
            force=force, extensions=list(extensions))
    if path is None:
        path = get_library_path(mode)
    return CGMDAT.get_ext_options(force, path=path, extensions=list(extensions))


def get_setup_library_options(force=False, path=None, mode='dev', modes=None):
    """Scan cgmDat/sim/setups for setup dat files. See get_library_options for modes."""
    if modes is None and isinstance(mode, (list, tuple)):
        modes = mode
    if modes is not None:
        return CGMDAT.get_ext_options_multi(
            modes=modes, path_join=['cgmDat', 'sim', 'setups'],
            force=force, extensions=[SETUP_EXTENSION])
    if path is None:
        path = get_setups_library_path(mode)
    return CGMDAT.get_ext_options(force, path=path, extensions=[SETUP_EXTENSION])


def get_library_rows(kind_ext=None, modes=None, force=True, setup=False):
    """
    Collective library menu rows for enabled SearchDir modes.

    kind_ext: if set, filter rows whose filepath ends with that extension.
    setup: scan setups instead of sim presets.
    Returns list of {key, filepath, mode, display}.
    """
    modes = CGMDAT.library_modes_normalize(modes)
    if setup:
        _rows, _ = get_setup_library_options(force=force, modes=modes)
    else:
        _rows, _ = get_library_options(force=force, modes=modes)
    if kind_ext:
        _suf = '.{0}'.format(kind_ext)
        _rows = [r for r in _rows if (r.get('filepath') or '').endswith(_suf)]
    return _rows


def seed_module_profile_to_file(profileName, datKind, outDir=None, differential=True):
    """Write one preset module entry to a dat file (dev seed helper)."""
    cls = dat_class_for_kind(datKind)
    if not cls:
        return False
    _dat = cls.from_module_profile(profileName, differential=differential)
    if not _dat:
        log.warning('Could not seed {0} ({1})'.format(profileName, datKind))
        return False
    inst = cls(dat=_dat)
    if outDir is None:
        outDir = inst.startDir_get(startDirMode='dev')
    os.makedirs(outDir, exist_ok=True)
    _path = os.path.join(outDir, '{0}.{1}'.format(profileName, cls._ext))
    return inst.write(filepath=_path, startDirMode='dev')


def seed_dev_library():
    """Export starter presets from Python modules into cgm/cgmDat/sim/."""
    _seeds = (
        ('hair', 'bob'),
        ('hair', 'bangs_firm'),
        ('cloth', 'cotton'),
        ('cloth', 'bangs_firm'),
        ('nucleus', 'solver_balanced'),
        ('nucleus', 'wind_calm'),
    )
    _results = []
    for kind, name in _seeds:
        _results.append(seed_module_profile_to_file(name, kind))
    return all(_results)
