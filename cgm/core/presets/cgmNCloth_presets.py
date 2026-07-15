#=========================================================================
# cgmNCloth_presets
# nCloth + nucleus profiles — fabric feel is separate from solver speed.
#
# Section keys:
#   'nc'  - nClothShape (fabric feel, stability helpers)
#   'n'   - nucleus (solver speed, wind, gravity env)
#
# Profile kinds (d_profileKind):
#   fabric  - material feel (nc only)
#   solver  - subSteps / collision iters / timeScale (n only)
#   wind    - nucleus wind / air (n only)
#   utility - one-shot resets (nc + n)
#
# Usage:
#   import cgm.core.lib.nCloth_utils as NCLOTH
#   NCLOTH.profile_load('cotton')                          # fabric only
#   NCLOTH.profile_load('cotton', solver='solver_quality') # fabric + solver
#   NCLOTH.profile_load('denim', solver='solver_preview', wind='wind_calm')
#=========================================================================

# Clean baseline. Merged first when clean=True.
base = {
    'n': {
        'gravity': 9.8,
        # Remapped to scene up at apply time (y-up -> [0,-1,0], z-up -> [0,0,-1]).
        'gravityDirection': [0.0, -1.0, 0.0],
        'airDensity': 1.0,
        'windSpeed': 0.0,
        'windNoise': 0.0,
        'windDirection': [1.0, 0.0, 0.0],
        'timeScale': 1.0,
        # cm scene units (Maya default). Use 1.0 if working in meters.
        'spaceScale': 0.01,
        'subSteps': 6,
        'maxCollisionIterations': 8,
        'usePlane': False,
        'planeFriction': 0.1,
        'planeBounce': 0.0,
        'planeStickiness': 0.0,
    },
    'nc': {
        'collide': True,
        'bounce': 0.0,
        'friction': 0.1,
        'stickiness': 0.0,
        'stretchResistance': 40.0,
        'compressionResistance': 20.0,
        'bendResistance': 0.5,
        'bendAngleDropoff': 0.4,
        'shearResistance': 40.0,
        'restitutionAngle': 360.0,
        'restitutionTension': 1000.0,
        'damp': 0.1,
        'drag': 0.05,
        'tangentialDrag': 0.0,
        'lift': 0.05,
        'pointMass': 1.0,
        'pushOut': 0.0,
        'pushOutRadius': 10.0,
        'rigidity': 0.0,
        'deformResistance': 0.0,
        'inputMeshAttract': 0.0,
        'inputAttractDamp': 0.5,
        'restLengthScale': 1.0,
        'pressure': 0.0,
        'pressureDamping': 0.0,
        'ignoreSolverGravity': False,
        'ignoreSolverWind': False,
        'localSpaceOutput': False,
    },
}

# Kind registry for menus / profile_load layering.
d_profileKind = {
    'base': 'base',
    # fabric — nc only
    'silk': 'fabric',
    'cotton': 'fabric',
    'denim': 'fabric',
    'leather': 'fabric',
    'flag': 'fabric',
    'stable': 'fabric',
    'rubber': 'fabric',
    'inputAttract': 'fabric',
    # solver — n only (pair with any fabric)
    'solver_balanced': 'solver',
    'solver_preview': 'solver',
    'solver_quality': 'solver',
    'solver_high': 'solver',
    # wind — n only
    'wind_calm': 'wind',
    'wind_flag': 'wind',
    # utility
    'calm': 'utility',
    # deprecated alias handled in nCloth_utils.profile_resolve
    'preview': 'solver',
}

# -------------------------------------------------------------------------
# Fabric (nc) — material feel only. Pair with a solver profile in the UI.
# -------------------------------------------------------------------------

silk = {
    'nc': {
        'pointMass': 0.35,
        'stretchResistance': 60.0,
        'compressionResistance': 10.0,
        'bendResistance': 0.05,
        'bendAngleDropoff': 0.6,
        'shearResistance': 30.0,
        'damp': 0.04,
        'drag': 0.08,
        'lift': 0.1,
        'friction': 0.05,
    },
}

cotton = {
    'nc': {
        'pointMass': 1.0,
        'stretchResistance': 50.0,
        'compressionResistance': 20.0,
        'bendResistance': 0.4,
        'bendAngleDropoff': 0.4,
        'shearResistance': 40.0,
        'damp': 0.1,
        'drag': 0.05,
        'lift': 0.05,
        'friction': 0.15,
    },
}

denim = {
    'nc': {
        'pointMass': 2.0,
        'stretchResistance': 120.0,
        'compressionResistance': 60.0,
        'bendResistance': 2.5,
        'bendAngleDropoff': 0.3,
        'shearResistance': 80.0,
        'damp': 0.22,
        'drag': 0.04,
        'friction': 0.4,
    },
}

leather = {
    'nc': {
        'pointMass': 2.5,
        'stretchResistance': 180.0,
        'compressionResistance': 100.0,
        'bendResistance': 12.0,
        'bendAngleDropoff': 0.2,
        'shearResistance': 120.0,
        'damp': 0.25,
        'drag': 0.03,
        'friction': 0.5,
        'deformResistance': 0.2,
    },
}

# Light cloth for flags/banners — add wind_flag for motion.
flag = {
    'nc': {
        'pointMass': 0.5,
        'stretchResistance': 80.0,
        'compressionResistance': 15.0,
        'bendResistance': 0.1,
        'bendAngleDropoff': 0.7,
        'shearResistance': 40.0,
        'damp': 0.05,
        'drag': 0.12,
        'lift': 0.15,
        'friction': 0.05,
    },
}

# Character apparel — stiff but damped; use solver_quality for collisions.
stable = {
    'nc': {
        'pointMass': 1.0,
        'stretchResistance': 200.0,
        'compressionResistance': 100.0,
        'bendResistance': 1.0,
        'bendAngleDropoff': 0.35,
        'shearResistance': 80.0,
        'damp': 0.2,
        'drag': 0.05,
        'friction': 0.2,
        'pushOut': 0.1,
        'pushOutRadius': 5.0,
        'inputMeshAttract': 0.15,
        'inputAttractDamp': 0.6,
    },
}

rubber = {
    'nc': {
        'pointMass': 1.2,
        'stretchResistance': 15.0,
        'compressionResistance': 10.0,
        'bendResistance': 0.8,
        'shearResistance': 20.0,
        'damp': 0.05,
        'bounce': 0.4,
        'friction': 0.6,
        'stickiness': 0.05,
        'drag': 0.04,
    },
}

inputAttract = {
    'nc': {
        'inputMeshAttract': 1.0,
        'inputAttractDamp': 0.5,
        'stretchResistance': 100.0,
        'bendResistance': 2.0,
        'damp': 0.2,
    },
}

# -------------------------------------------------------------------------
# Solver (n) — speed / quality only. Does not change fabric feel.
# -------------------------------------------------------------------------

solver_balanced = {
    'n': {
        'subSteps': 6,
        'maxCollisionIterations': 8,
        'timeScale': 1.0,
    },
}

solver_preview = {
    'n': {
        'subSteps': 3,
        'maxCollisionIterations': 4,
        'timeScale': 1.0,
    },
}

solver_quality = {
    'n': {
        'subSteps': 8,
        'maxCollisionIterations': 12,
        'timeScale': 1.0,
    },
}

solver_high = {
    'n': {
        'subSteps': 20,
        'maxCollisionIterations': 50,
        'timeScale': 1.0,
    },
}

# -------------------------------------------------------------------------
# Wind (n) — environment only.
# -------------------------------------------------------------------------

wind_calm = {
    'n': {
        'windSpeed': 0.0,
        'windNoise': 0.0,
        'airDensity': 1.0,
    },
}

wind_flag = {
    'n': {
        'airDensity': 1.5,
        'windSpeed': 8.0,
        'windNoise': 2.0,
        'windDirection': [1.0, 0.0, 0.0],
    },
}

# -------------------------------------------------------------------------
# Utility — quick reset (wind off + mild nc defaults).
# -------------------------------------------------------------------------

calm = {
    'n': {
        'windSpeed': 0.0,
        'windNoise': 0.0,
        'airDensity': 1.0,
        'usePlane': False,
    },
    'nc': {
        'pressure': 0.0,
        'lift': 0.05,
        'drag': 0.05,
        'ignoreSolverWind': False,
        'ignoreSolverGravity': False,
    },
}
