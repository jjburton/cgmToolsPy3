import tempfile
from cgm.lib import files
import maya.cmds as mc

import cgm.core.tools.Project as PROJECT
from cgm.core.tools.stableDiffusion import stableDiffusionTools as sd
from cgm.core.tools.stableDiffusion import renderTools as rt
from cgm.core.tools import imageViewer as iv
from cgm.core.tools import imageTools as it

import os
import base64
import traceback
from PIL import Image, ImageFilter
from io import BytesIO
import logging

logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

def displayImage(imagePaths, data={}, callbackData=[]):
    log.debug(f"Displaying images: {imagePaths}")
    iv.ui(imagePaths, data, callbackData)

def getMeshesAndCamera(self):
    _str_func = "generateImage.getMeshesAndCamera"

    meshes = self.uiList_projectionMeshes(q=True, allItems=True)
    camera = self.uiTextField_projectionCamera(q=True, text=True)

    if not camera:
        log.warning("|{0}| >> No camera loaded.".format(_str_func))

    if meshes is None or len(meshes) == 0:
        log.warning("|{0}| >> No meshes loaded.".format(_str_func))
    
    return meshes, camera

def setButtonProperties(button, state, label=None, bgColor=None):
    button(edit=True, enable=state)
    if label is not None:
        button(edit=True, label=label)
    button(edit=True, bgc=bgColor)

def processImg2Img(self, meshes, camera, _options):
    _str_func = "generateImage.processImg2Img"

    option = _options["img2img_pass"].lower()
    log.debug("img2img_pass {0}".format(option))

    if option != "none":
        if option == "composite" or option == "merged":          
            self.uiFunc_assignMaterial(option, meshes)

            scaleMult = float(self.uiOM_img2imgScaleMultiplier.getValue())
            wantedResolution = (
                self.resolution[0] * scaleMult,
                self.resolution[1] * scaleMult,
            )

            log.debug(
                "rendering composite image at resolution {0}".format(
                    wantedResolution
                )
            )
            composite_path = rt.renderMaterialPass(
                camera=camera, format="jpg", resolution=wantedResolution
            )

            log.debug("composite path: {0}".format(composite_path))

            _options["init_images"] = [it.encodeImageToString(composite_path)]

        elif option == "custom":
            custom_image = self.uiTextField_customImage(query=True, text=True)
            log.debug("custom image: {0}".format(custom_image))
            
            if os.path.exists(custom_image):
                with open(custom_image, "rb") as c:
                    # Read the image data
                    composite_data = c.read()

                    # Encode the image data as base64
                    composite_base64 = base64.b64encode(composite_data)

                    # Convert the base64 bytes to string
                    composite_string = composite_base64.decode("utf-8")

                    c.close()

                _options["init_images"] = [composite_string]
        elif option == "render layer":
            outputImage = self.uiFunc_renderLayer(display=False)
            log.debug("render layer: {0}".format(outputImage))

            if outputImage:
                _options["init_images"] = [it.encodeImageToString(outputImage)]

def processControlNets(self, meshes, camera, _options):
    _str_func = "generateImage.processControlNets"

    # Get Control Nets
    for i in range(4):
        _controlNetOptions = _options['control_nets'][i]

        if not _controlNetOptions['control_net_enabled']:
            continue
        
        preprocessor = self.controlNets[i]['preprocessor_menu'](q=True, value=True)
        if self.controlNets[i]['custom_image_cb'].getValue():
            control_net_image_path = ""
            if self.controlNets[i]['custom_image_cb'].getValue():
                control_net_image_path = self.controlNets[i]['custom_image_tf'].getValue()
            
            if os.path.exists(control_net_image_path):
                _controlNetOptions["control_net_image"] = it.encodeImageToString(control_net_image_path)
        elif preprocessor == "none":

            imgMode = None
            if 'depth' in _controlNetOptions["control_net_model"]:
                imgMode = "depth"
            elif 'normal' in _controlNetOptions["control_net_model"]:
                imgMode = "normal"                

            depthMat = self.uiFunc_getMaterial(imgMode)

            if not depthMat or not mc.objExists(depthMat):
                log.warning("|{0}| >> No {1} shader loaded.".format(_str_func, imgMode))
                # prompt to create one
                result = mc.confirmDialog(
                    title="No {0} shader loaded".format(imgMode),
                    message="No depth shader loaded. Would you like to create one?",
                    button=["Yes", "No"],
                    defaultButton="Yes",
                    cancelButton="No",
                    dismissString="No",
                )
                if result == "Yes":
                    if imgMode == "depth":
                        depthMat, sg = self.uiFunc_makeDepthShader()
                        self.uiFunc_guessDepth()
                    elif imgMode == "normal":
                        depthMat, sg = self.uiFunc_makeNormalShader()

            if mc.objExists(depthMat) and meshes:
                format = "png"
                self.uiFunc_assignMaterial(imgMode, meshes)

                if _options["auto_depth_enabled"] and imgMode == "depth":
                    self.uiFunc_guessDepth()

                depth_path = rt.renderMaterialPass(
                    fileName="{0}Pass".format(imgMode.capitalize()), camera=camera, resolution=self.resolution
                )

                log.debug("{0}_path: {1}".format(imgMode, depth_path))
                # Read the image data
                depth_image = Image.open(depth_path)

                if(imgMode == "depth"):
                    # depth_image = depth_image.filter(ImageFilter.GaussianBlur(3))
                    depth_image = it.addMonochromaticNoise(
                        depth_image, _controlNetOptions["control_net_noise"], 1
                    )

                # Convert the image data to grayscale
                depth_image_RGB = depth_image.convert("RGB")

                # Encode the image data as base64
                # depth_buffered = BytesIO()
                with BytesIO() as depth_buffered:
                    depth_image_RGB.save(depth_buffered, format=format)

                    depth_base64 = base64.b64encode(depth_buffered.getvalue())

                    # Convert the base64 bytes to string
                    depth_string = depth_base64.decode("utf-8")

                    _controlNetOptions["control_net_image"] = depth_string
            else:
                log.warning(
                    "|{0}| >> No depth shader loaded. Disabling Control Net".format(
                        _str_func
                    )
                )
                _controlNetOptions["control_net_enabled"] = False
        else:
            self.uiFunc_assignMaterial("composite", meshes)

            control_net_image_path = rt.renderMaterialPass(
                fileName="CustomPass", camera=camera, resolution=self.resolution
            )

            if os.path.exists(control_net_image_path):
                _controlNetOptions["control_net_image"] = it.encodeImageToString(control_net_image_path)

        _options['control_nets'][i] = _controlNetOptions

def getImageAndUpdateUI(self, _options, cameraInfo, origText, bgColor, display=True):
    try:            
        imagePaths, info = sd.getImageFromAutomatic1111(_options)

        log.debug(f"Generated: {imagePaths} {info}")

        if imagePaths:
            callbacks = []
            callbacks.append(
                {"label": "Make Plane", "function": rt.makeImagePlane}
            )
            callbacks.append(
                {
                    "label": "Set As Custom Image",
                    "function": self.setAsCustomImage,
                }
            )
            callbacks.append(
                {
                    "label": "Set As Projection",
                    "function": self.assignImageToProjection,
                }
            )
            callbacks.append(
                {
                    "label": "Regenerate",
                    "function": self.generateFromImageData,
                }
            )

            if "latent_batch" in _options.keys() and _options["latent_batch"]:
                callbacks.append(
                    {
                        "label": "Bake LSP on Selected",
                        "function": self.uiFunc_bakeLatentSpaceImageOnSelected,
                    }
                )
                info['latent_batch'] = True
                log.debug(f"latent_batch_num_images from getImageAndUpdate: {_options['latent_batch_num_images']}")
                info['latent_batch_num_images'] = _options['latent_batch_num_images']
                info['latent_batch_camera_info'] = _options['latent_batch_camera_info']

            if display:
                displayImage(imagePaths, info, callbacks)

        info["camera_info"] = cameraInfo

        self.lastInfo = info

        setButtonProperties(self.generateBtn, True, origText, bgColor)

        return imagePaths, info
    except Exception:
        # display full error in log
        e = traceback.format_exc()
        log.error(e)

        setButtonProperties(self.generateBtn, True, origText, bgColor)

        return [], {"error": e}

def processAlphaMatte(self, meshes, camera, _options):
    _str_func = "generateImage.processAlphaMatte"
    
    if _options["use_alpha_pass"] and _options["img2img_pass"] != "none" and meshes:
        self.uiFunc_assignMaterial("alphaMatte", meshes)

        alpha_path = rt.renderMaterialPass(
            fileName="AlphaPass", camera=camera, resolution=self.resolution
        )

        log.debug("alpha_path: {0}".format(alpha_path))

        if os.path.exists(alpha_path):
            # Read the image data
            alpha_image = Image.open(alpha_path)

            # Convert the image data to grayscale
            alpha_image_gray = alpha_image.convert("L")

            # Encode the image data as base64
            buffered = BytesIO()
            alpha_image_gray.save(buffered, format="PNG")

            alpha_base64 = base64.b64encode(buffered.getvalue())

            # Convert the base64 bytes to string
            alpha_string = alpha_base64.decode("utf-8")

            _options["mask"] = alpha_string
            _options["mask_blur"] = self.uiIF_maskBlur(query=True, value=True)
            _options["inpainting_mask_invert"] = 1
        else:
            log.warning("|{0}| >> No alpha matte found.".format(_str_func))

def getCameraInfo(camera):
    cameraInfo = {}
    if camera:
        cameraTransform = mc.listRelatives(camera, parent=True)[0]
        cameraInfo = {
            "position": mc.xform(cameraTransform, q=True, ws=True, t=True),
            "rotation": mc.xform(cameraTransform, q=True, ws=True, ro=True),
            "fov": mc.getAttr(camera + ".focalLength"),
        }
    return cameraInfo

def generateImageFromUI(self, display=True):
    _str_func = "generateImage.generateImageFromUI"

    # alphaMat = self.uiTextField_alphaMatteShader(q=True, text=True)
    #
    meshes, camera = getMeshesAndCamera(self)

    bgColor = self.generateBtn(q=True, bgc=True)
    origText = self.generateBtn(q=True, label=True)
    setButtonProperties(self.generateBtn, False, "Generating...", (1, 0.5, 0.5))

    mc.refresh()

    _options = self.getOptions()  

    # standardize the output path
    output_path = os.path.normpath(
        os.path.join(PROJECT.getImagePath(), "sd_output")
    )
    _options["output_path"] = output_path

    _latentBatch = self.uiOM_batchMode.getValue() == "Latent Space"

    self.uiFunc_setSize("field")

    if _latentBatch:
        frames = range(
            self.uiIF_batchProjectStart.getValue(),
            self.uiIF_batchProjectEnd.getValue()+1,
            self.uiIF_batchProjectStep.getValue(),
        )

        img2img_images = []
        controlNet_images = [[] for x in range(4)]
        alpha_images = []
        _options['latent_batch_camera_info'] = []

        for i in frames:
            mc.currentTime(i)
            processImg2Img(self, meshes, camera, _options)
            if "init_images" in _options.keys():
                if len(_options["init_images"]) > 0:
                    img2img_images.append(_options["init_images"][0])
            
            processControlNets(self, meshes, camera, _options)
            for p in range(4):
                if _options['control_nets'][p]['control_net_enabled']:
                    controlNet_images[p].append(_options['control_nets'][p]['control_net_image'])

            processAlphaMatte(self, meshes, camera, _options)
            if "mask" in _options.keys():
                alpha_images.append(_options["mask"])
            
            frameCamInfo = getCameraInfo(camera)
            frameCamInfo['frame'] = i
            _options['latent_batch_camera_info'].append(frameCamInfo)

        setButtonProperties(self.generateBtn, True, origText, bgColor)

        tmpdir = tempfile.TemporaryDirectory().name
        os.mkdir(tmpdir)
        log.debug(f"Created temporary directory: {tmpdir}")

        resolution = (_options["width"], _options["height"])

        if len(img2img_images) > 0:
            log.debug(f"len img2img_images: {len(img2img_images)}")

            contactSheet = it.createContactSheetFromStrings(img2img_images)
            wantedName = os.path.join(tmpdir, "img2img_contact_sheet.jpg")
            wantedName = files.create_unique_filename(wantedName)
            contactSheet.save(wantedName)
            log.debug(f"img2img_images: {wantedName}")
            _options["init_images"] = [it.encodeImageToString(wantedName)]
            resolution = (contactSheet.width, contactSheet.height)
        for i in range(4):
            if len(controlNet_images[i]) > 0:
                log.debug(f"len controlNet_images[{i}]: {len(controlNet_images[i])}")
                contactSheet = it.createContactSheetFromStrings(controlNet_images[i])
                wantedName = os.path.join(tmpdir, "controlnet_%s_contact_sheet.png"%i)
                wantedName = files.create_unique_filename(wantedName)
                contactSheet.save(wantedName)
                log.debug(f"controlNet_images[{i}]: {wantedName}")
                _options['control_nets'][i]['control_net_image'] = it.encodeImageToString(wantedName)
                resolution = (contactSheet.width, contactSheet.height)
        if len(alpha_images) > 0:
            contactSheet = it.createContactSheetFromStrings(controlNet_images[i])
            wantedName = os.path.join(tmpdir, "alpha_contact_sheet.png")
            wantedName = files.create_unique_filename(wantedName)
            contactSheet.save(wantedName)
            log.debug(f"alpha_images: {wantedName}")
            _options["mask"] = it.encodeImageToString(wantedName)
            resolution = (contactSheet.width, contactSheet.height)
        
        _options["latent_batch"] = True
        _options["latent_batch_num_images"] = len(_options['latent_batch_camera_info'])
        log.debug(f"latent_batch_num_images from generateImageFromUI: {_options['latent_batch_num_images']}")

        _options["width"] = resolution[0]
        _options["height"] = resolution[1]
    else:
        processImg2Img(self, meshes, camera, _options)
        processControlNets(self, meshes, camera, _options)
        processAlphaMatte(self, meshes, camera, _options)

    cameraInfo = getCameraInfo(camera)

    return getImageAndUpdateUI(self, _options, cameraInfo, origText, bgColor, display)

    # Start a new thread to get the image and update the UI
    # threading.Thread(target=get_image_and_update_ui).start()