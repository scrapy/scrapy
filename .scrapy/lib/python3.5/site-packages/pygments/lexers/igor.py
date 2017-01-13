# -*- coding: utf-8 -*-
"""
    pygments.lexers.igor
    ~~~~~~~~~~~~~~~~~~~~

    Lexers for Igor Pro.

    :copyright: Copyright 2006-2015 by the Pygments team, see AUTHORS.
    :license: BSD, see LICENSE for details.
"""

import re

from pygments.lexer import RegexLexer, words
from pygments.token import Text, Comment, Keyword, Name, String

__all__ = ['IgorLexer']


class IgorLexer(RegexLexer):
    """
    Pygments Lexer for Igor Pro procedure files (.ipf).
    See http://www.wavemetrics.com/ and http://www.igorexchange.com/.

    .. versionadded:: 2.0
    """

    name = 'Igor'
    aliases = ['igor', 'igorpro']
    filenames = ['*.ipf']
    mimetypes = ['text/ipf']

    flags = re.IGNORECASE | re.MULTILINE

    flowControl = (
        'if', 'else', 'elseif', 'endif', 'for', 'endfor', 'strswitch', 'switch',
        'case', 'default', 'endswitch', 'do', 'while', 'try', 'catch', 'endtry',
        'break', 'continue', 'return', 'AbortOnRTE', 'AbortOnValue'
    )
    types = (
        'variable', 'string', 'constant', 'strconstant', 'NVAR', 'SVAR', 'WAVE',
        'STRUCT', 'dfref', 'funcref', 'char', 'uchar', 'int16', 'uint16', 'int32',
        'uint32', 'float', 'double'
    )
    keywords = (
        'override', 'ThreadSafe', 'MultiThread', 'static',  'Proc',
        'Picture', 'Prompt', 'DoPrompt', 'macro', 'window', 'function', 'end',
        'Structure', 'EndStructure', 'EndMacro', 'Menu', 'SubMenu'
    )
    operations = (
        'Abort', 'AddFIFOData', 'AddFIFOVectData', 'AddMovieAudio',
        'AddMovieFrame', 'APMath', 'Append', 'AppendImage',
        'AppendLayoutObject', 'AppendMatrixContour', 'AppendText',
        'AppendToGraph', 'AppendToLayout', 'AppendToTable', 'AppendXYZContour',
        'AutoPositionWindow', 'BackgroundInfo', 'Beep', 'BoundingBall',
        'BrowseURL', 'BuildMenu', 'Button', 'cd', 'Chart', 'CheckBox',
        'CheckDisplayed', 'ChooseColor', 'Close', 'CloseMovie', 'CloseProc',
        'ColorScale', 'ColorTab2Wave', 'Concatenate', 'ControlBar',
        'ControlInfo', 'ControlUpdate', 'ConvexHull', 'Convolve', 'CopyFile',
        'CopyFolder', 'CopyScales', 'Correlate', 'CreateAliasShortcut', 'Cross',
        'CtrlBackground', 'CtrlFIFO', 'CtrlNamedBackground', 'Cursor',
        'CurveFit', 'CustomControl', 'CWT', 'Debugger', 'DebuggerOptions',
        'DefaultFont', 'DefaultGuiControls', 'DefaultGuiFont', 'DefineGuide',
        'DelayUpdate', 'DeleteFile', 'DeleteFolder', 'DeletePoints',
        'Differentiate', 'dir', 'Display', 'DisplayHelpTopic',
        'DisplayProcedure', 'DoAlert', 'DoIgorMenu', 'DoUpdate', 'DoWindow',
        'DoXOPIdle', 'DrawAction', 'DrawArc', 'DrawBezier', 'DrawLine',
        'DrawOval', 'DrawPICT', 'DrawPoly', 'DrawRect', 'DrawRRect', 'DrawText',
        'DSPDetrend', 'DSPPeriodogram', 'Duplicate', 'DuplicateDataFolder',
        'DWT', 'EdgeStats', 'Edit', 'ErrorBars', 'Execute', 'ExecuteScriptText',
        'ExperimentModified', 'Extract', 'FastGaussTransform', 'FastOp',
        'FBinRead', 'FBinWrite', 'FFT', 'FIFO2Wave', 'FIFOStatus', 'FilterFIR',
        'FilterIIR', 'FindLevel', 'FindLevels', 'FindPeak', 'FindPointsInPoly',
        'FindRoots', 'FindSequence', 'FindValue', 'FPClustering', 'fprintf',
        'FReadLine', 'FSetPos', 'FStatus', 'FTPDelete', 'FTPDownload',
        'FTPUpload', 'FuncFit', 'FuncFitMD', 'GetAxis', 'GetFileFolderInfo',
        'GetLastUserMenuInfo', 'GetMarquee', 'GetSelection', 'GetWindow',
        'GraphNormal', 'GraphWaveDraw', 'GraphWaveEdit', 'Grep', 'GroupBox',
        'Hanning', 'HideIgorMenus', 'HideInfo', 'HideProcedures', 'HideTools',
        'HilbertTransform', 'Histogram', 'IFFT', 'ImageAnalyzeParticles',
        'ImageBlend', 'ImageBoundaryToMask', 'ImageEdgeDetection',
        'ImageFileInfo', 'ImageFilter', 'ImageFocus', 'ImageGenerateROIMask',
        'ImageHistModification', 'ImageHistogram', 'ImageInterpolate',
        'ImageLineProfile', 'ImageLoad', 'ImageMorphology', 'ImageRegistration',
        'ImageRemoveBackground', 'ImageRestore', 'ImageRotate', 'ImageSave',
        'ImageSeedFill', 'ImageSnake', 'ImageStats', 'ImageThreshold',
        'ImageTransform', 'ImageUnwrapPhase', 'ImageWindow', 'IndexSort',
        'InsertPoints', 'Integrate', 'IntegrateODE', 'Interp3DPath',
        'Interpolate3D', 'KillBackground', 'KillControl', 'KillDataFolder',
        'KillFIFO', 'KillFreeAxis', 'KillPath', 'KillPICTs', 'KillStrings',
        'KillVariables', 'KillWaves', 'KillWindow', 'KMeans', 'Label', 'Layout',
        'Legend', 'LinearFeedbackShiftRegister', 'ListBox', 'LoadData',
        'LoadPackagePreferences', 'LoadPICT', 'LoadWave', 'Loess',
        'LombPeriodogram', 'Make', 'MakeIndex', 'MarkPerfTestTime',
        'MatrixConvolve', 'MatrixCorr', 'MatrixEigenV', 'MatrixFilter',
        'MatrixGaussJ', 'MatrixInverse', 'MatrixLinearSolve',
        'MatrixLinearSolveTD', 'MatrixLLS', 'MatrixLUBkSub', 'MatrixLUD',
        'MatrixMultiply', 'MatrixOP', 'MatrixSchur', 'MatrixSolve',
        'MatrixSVBkSub', 'MatrixSVD', 'MatrixTranspose', 'MeasureStyledText',
        'Modify', 'ModifyContour', 'ModifyControl', 'ModifyControlList',
        'ModifyFreeAxis', 'ModifyGraph', 'ModifyImage', 'ModifyLayout',
        'ModifyPanel', 'ModifyTable', 'ModifyWaterfall', 'MoveDataFolder',
        'MoveFile', 'MoveFolder', 'MoveString', 'MoveSubwindow', 'MoveVariable',
        'MoveWave', 'MoveWindow', 'NeuralNetworkRun', 'NeuralNetworkTrain',
        'NewDataFolder', 'NewFIFO', 'NewFIFOChan', 'NewFreeAxis', 'NewImage',
        'NewLayout', 'NewMovie', 'NewNotebook', 'NewPanel', 'NewPath',
        'NewWaterfall', 'Note', 'Notebook', 'NotebookAction', 'Open',
        'OpenNotebook', 'Optimize', 'ParseOperationTemplate', 'PathInfo',
        'PauseForUser', 'PauseUpdate', 'PCA', 'PlayMovie', 'PlayMovieAction',
        'PlaySnd', 'PlaySound', 'PopupContextualMenu', 'PopupMenu',
        'Preferences', 'PrimeFactors', 'Print', 'printf', 'PrintGraphs',
        'PrintLayout', 'PrintNotebook', 'PrintSettings', 'PrintTable',
        'Project', 'PulseStats', 'PutScrapText', 'pwd', 'Quit',
        'RatioFromNumber', 'Redimension', 'Remove', 'RemoveContour',
        'RemoveFromGraph', 'RemoveFromLayout', 'RemoveFromTable', 'RemoveImage',
        'RemoveLayoutObjects', 'RemovePath', 'Rename', 'RenameDataFolder',
        'RenamePath', 'RenamePICT', 'RenameWindow', 'ReorderImages',
        'ReorderTraces', 'ReplaceText', 'ReplaceWave', 'Resample',
        'ResumeUpdate', 'Reverse', 'Rotate', 'Save', 'SaveData',
        'SaveExperiment', 'SaveGraphCopy', 'SaveNotebook',
        'SavePackagePreferences', 'SavePICT', 'SaveTableCopy',
        'SetActiveSubwindow', 'SetAxis', 'SetBackground', 'SetDashPattern',
        'SetDataFolder', 'SetDimLabel', 'SetDrawEnv', 'SetDrawLayer',
        'SetFileFolderInfo', 'SetFormula', 'SetIgorHook', 'SetIgorMenuMode',
        'SetIgorOption', 'SetMarquee', 'SetProcessSleep', 'SetRandomSeed',
        'SetScale', 'SetVariable', 'SetWaveLock', 'SetWindow', 'ShowIgorMenus',
        'ShowInfo', 'ShowTools', 'Silent', 'Sleep', 'Slider', 'Smooth',
        'SmoothCustom', 'Sort', 'SoundInRecord', 'SoundInSet',
        'SoundInStartChart', 'SoundInStatus', 'SoundInStopChart',
        'SphericalInterpolate', 'SphericalTriangulate', 'SplitString',
        'sprintf', 'sscanf', 'Stack', 'StackWindows',
        'StatsAngularDistanceTest', 'StatsANOVA1Test', 'StatsANOVA2NRTest',
        'StatsANOVA2RMTest', 'StatsANOVA2Test', 'StatsChiTest',
        'StatsCircularCorrelationTest', 'StatsCircularMeans',
        'StatsCircularMoments', 'StatsCircularTwoSampleTest',
        'StatsCochranTest', 'StatsContingencyTable', 'StatsDIPTest',
        'StatsDunnettTest', 'StatsFriedmanTest', 'StatsFTest',
        'StatsHodgesAjneTest', 'StatsJBTest', 'StatsKendallTauTest',
        'StatsKSTest', 'StatsKWTest', 'StatsLinearCorrelationTest',
        'StatsLinearRegression', 'StatsMultiCorrelationTest',
        'StatsNPMCTest', 'StatsNPNominalSRTest', 'StatsQuantiles',
        'StatsRankCorrelationTest', 'StatsResample', 'StatsSample',
        'StatsScheffeTest', 'StatsSignTest', 'StatsSRTest', 'StatsTTest',
        'StatsTukeyTest', 'StatsVariancesTest', 'StatsWatsonUSquaredTest',
        'StatsWatsonWilliamsTest', 'StatsWheelerWatsonTest',
        'StatsWilcoxonRankTest', 'StatsWRCorrelationTest', 'String',
        'StructGet', 'StructPut', 'TabControl', 'Tag', 'TextBox', 'Tile',
        'TileWindows', 'TitleBox', 'ToCommandLine', 'ToolsGrid',
        'Triangulate3d', 'Unwrap', 'ValDisplay', 'Variable', 'WaveMeanStdv',
        'WaveStats', 'WaveTransform', 'wfprintf', 'WignerTransform',
        'WindowFunction',
    )
    functions = (
        'abs', 'acos', 'acosh', 'AiryA', 'AiryAD', 'AiryB', 'AiryBD', 'alog',
        'area', 'areaXY', 'asin', 'asinh', 'atan', 'atan2', 'atanh',
        'AxisValFromPixel', 'Besseli', 'Besselj', 'Besselk', 'Bessely', 'bessi',
        'bessj', 'bessk', 'bessy', 'beta', 'betai', 'BinarySearch',
        'BinarySearchInterp', 'binomial', 'binomialln', 'binomialNoise', 'cabs',
        'CaptureHistoryStart', 'ceil', 'cequal', 'char2num', 'chebyshev',
        'chebyshevU', 'CheckName', 'cmplx', 'cmpstr', 'conj', 'ContourZ', 'cos',
        'cosh', 'cot', 'CountObjects', 'CountObjectsDFR', 'cpowi',
        'CreationDate', 'csc', 'DataFolderExists', 'DataFolderRefsEqual',
        'DataFolderRefStatus', 'date2secs', 'datetime', 'DateToJulian',
        'Dawson', 'DDEExecute', 'DDEInitiate', 'DDEPokeString', 'DDEPokeWave',
        'DDERequestWave', 'DDEStatus', 'DDETerminate', 'defined', 'deltax', 'digamma',
        'DimDelta', 'DimOffset', 'DimSize', 'ei', 'enoise', 'equalWaves', 'erf',
        'erfc', 'exists', 'exp', 'expInt', 'expNoise', 'factorial', 'fakedata',
        'faverage', 'faverageXY', 'FindDimLabel', 'FindListItem', 'floor',
        'FontSizeHeight', 'FontSizeStringWidth', 'FresnelCos', 'FresnelSin',
        'gamma', 'gammaInc', 'gammaNoise', 'gammln', 'gammp', 'gammq', 'Gauss',
        'Gauss1D', 'Gauss2D', 'gcd', 'GetDefaultFontSize',
        'GetDefaultFontStyle', 'GetKeyState', 'GetRTError', 'gnoise',
        'GrepString', 'hcsr', 'hermite', 'hermiteGauss', 'HyperG0F1',
        'HyperG1F1', 'HyperG2F1', 'HyperGNoise', 'HyperGPFQ', 'IgorVersion',
        'ilim', 'imag', 'Inf', 'Integrate1D', 'interp', 'Interp2D', 'Interp3D',
        'inverseERF', 'inverseERFC', 'ItemsInList', 'jlim', 'Laguerre',
        'LaguerreA', 'LaguerreGauss', 'leftx', 'LegendreA', 'limit', 'ln',
        'log', 'logNormalNoise', 'lorentzianNoise', 'magsqr', 'MandelbrotPoint',
        'MarcumQ', 'MatrixDet', 'MatrixDot', 'MatrixRank', 'MatrixTrace', 'max',
        'mean', 'min', 'mod', 'ModDate', 'NaN', 'norm', 'NumberByKey',
        'numpnts', 'numtype', 'NumVarOrDefault', 'NVAR_Exists', 'p2rect',
        'ParamIsDefault', 'pcsr', 'Pi', 'PixelFromAxisVal', 'pnt2x',
        'poissonNoise', 'poly', 'poly2D', 'PolygonArea', 'qcsr', 'r2polar',
        'real', 'rightx', 'round', 'sawtooth', 'ScreenResolution', 'sec',
        'SelectNumber', 'sign', 'sin', 'sinc', 'sinh', 'SphericalBessJ',
        'SphericalBessJD', 'SphericalBessY', 'SphericalBessYD',
        'SphericalHarmonics', 'sqrt', 'StartMSTimer', 'StatsBetaCDF',
        'StatsBetaPDF', 'StatsBinomialCDF', 'StatsBinomialPDF',
        'StatsCauchyCDF', 'StatsCauchyPDF', 'StatsChiCDF', 'StatsChiPDF',
        'StatsCMSSDCDF', 'StatsCorrelation', 'StatsDExpCDF', 'StatsDExpPDF',
        'StatsErlangCDF', 'StatsErlangPDF', 'StatsErrorPDF', 'StatsEValueCDF',
        'StatsEValuePDF', 'StatsExpCDF', 'StatsExpPDF', 'StatsFCDF',
        'StatsFPDF', 'StatsFriedmanCDF', 'StatsGammaCDF', 'StatsGammaPDF',
        'StatsGeometricCDF', 'StatsGeometricPDF', 'StatsHyperGCDF',
        'StatsHyperGPDF', 'StatsInvBetaCDF', 'StatsInvBinomialCDF',
        'StatsInvCauchyCDF', 'StatsInvChiCDF', 'StatsInvCMSSDCDF',
        'StatsInvDExpCDF', 'StatsInvEValueCDF', 'StatsInvExpCDF',
        'StatsInvFCDF', 'StatsInvFriedmanCDF', 'StatsInvGammaCDF',
        'StatsInvGeometricCDF', 'StatsInvKuiperCDF', 'StatsInvLogisticCDF',
        'StatsInvLogNormalCDF', 'StatsInvMaxwellCDF', 'StatsInvMooreCDF',
        'StatsInvNBinomialCDF', 'StatsInvNCChiCDF', 'StatsInvNCFCDF',
        'StatsInvNormalCDF', 'StatsInvParetoCDF', 'StatsInvPoissonCDF',
        'StatsInvPowerCDF', 'StatsInvQCDF', 'StatsInvQpCDF',
        'StatsInvRayleighCDF', 'StatsInvRectangularCDF', 'StatsInvSpearmanCDF',
        'StatsInvStudentCDF', 'StatsInvTopDownCDF', 'StatsInvTriangularCDF',
        'StatsInvUsquaredCDF', 'StatsInvVonMisesCDF', 'StatsInvWeibullCDF',
        'StatsKuiperCDF', 'StatsLogisticCDF', 'StatsLogisticPDF',
        'StatsLogNormalCDF', 'StatsLogNormalPDF', 'StatsMaxwellCDF',
        'StatsMaxwellPDF', 'StatsMedian', 'StatsMooreCDF', 'StatsNBinomialCDF',
        'StatsNBinomialPDF', 'StatsNCChiCDF', 'StatsNCChiPDF', 'StatsNCFCDF',
        'StatsNCFPDF', 'StatsNCTCDF', 'StatsNCTPDF', 'StatsNormalCDF',
        'StatsNormalPDF', 'StatsParetoCDF', 'StatsParetoPDF', 'StatsPermute',
        'StatsPoissonCDF', 'StatsPoissonPDF', 'StatsPowerCDF',
        'StatsPowerNoise', 'StatsPowerPDF', 'StatsQCDF', 'StatsQpCDF',
        'StatsRayleighCDF', 'StatsRayleighPDF', 'StatsRectangularCDF',
        'StatsRectangularPDF', 'StatsRunsCDF', 'StatsSpearmanRhoCDF',
        'StatsStudentCDF', 'StatsStudentPDF', 'StatsTopDownCDF',
        'StatsTriangularCDF', 'StatsTriangularPDF', 'StatsTrimmedMean',
        'StatsUSquaredCDF', 'StatsVonMisesCDF', 'StatsVonMisesNoise',
        'StatsVonMisesPDF', 'StatsWaldCDF', 'StatsWaldPDF', 'StatsWeibullCDF',
        'StatsWeibullPDF', 'StopMSTimer', 'str2num', 'stringCRC', 'stringmatch',
        'strlen', 'strsearch', 'StudentA', 'StudentT', 'sum', 'SVAR_Exists',
        'TagVal', 'tan', 'tanh', 'ThreadGroupCreate', 'ThreadGroupRelease',
        'ThreadGroupWait', 'ThreadProcessorCount', 'ThreadReturnValue', 'ticks',
        'trunc', 'Variance', 'vcsr', 'WaveCRC', 'WaveDims', 'WaveExists',
        'WaveMax', 'WaveMin', 'WaveRefsEqual', 'WaveType', 'WhichListItem',
        'WinType', 'WNoise', 'x2pnt', 'xcsr', 'zcsr', 'ZernikeR',
    )
    functions += (
        'AddListItem', 'AnnotationInfo', 'AnnotationList', 'AxisInfo',
        'AxisList', 'CaptureHistory', 'ChildWindowList', 'CleanupName',
        'ContourInfo', 'ContourNameList', 'ControlNameList', 'CsrInfo',
        'CsrWave', 'CsrXWave', 'CTabList', 'DataFolderDir', 'date',
        'DDERequestString', 'FontList', 'FuncRefInfo', 'FunctionInfo',
        'FunctionList', 'FunctionPath', 'GetDataFolder', 'GetDefaultFont',
        'GetDimLabel', 'GetErrMessage', 'GetFormula',
        'GetIndependentModuleName', 'GetIndexedObjName', 'GetIndexedObjNameDFR',
        'GetRTErrMessage', 'GetRTStackInfo', 'GetScrapText', 'GetUserData',
        'GetWavesDataFolder', 'GrepList', 'GuideInfo', 'GuideNameList', 'Hash',
        'IgorInfo', 'ImageInfo', 'ImageNameList', 'IndexedDir', 'IndexedFile',
        'JulianToDate', 'LayoutInfo', 'ListMatch', 'LowerStr', 'MacroList',
        'NameOfWave', 'note', 'num2char', 'num2istr', 'num2str',
        'OperationList', 'PadString', 'ParseFilePath', 'PathList', 'PICTInfo',
        'PICTList', 'PossiblyQuoteName', 'ProcedureText', 'RemoveByKey',
        'RemoveEnding', 'RemoveFromList', 'RemoveListItem',
        'ReplaceNumberByKey', 'ReplaceString', 'ReplaceStringByKey',
        'Secs2Date', 'Secs2Time', 'SelectString', 'SortList',
        'SpecialCharacterInfo', 'SpecialCharacterList', 'SpecialDirPath',
        'StringByKey', 'StringFromList', 'StringList', 'StrVarOrDefault',
        'TableInfo', 'TextFile', 'ThreadGroupGetDF', 'time', 'TraceFromPixel',
        'TraceInfo', 'TraceNameList', 'UniqueName', 'UnPadString', 'UpperStr',
        'VariableList', 'WaveInfo', 'WaveList', 'WaveName', 'WaveUnits',
        'WinList', 'WinName', 'WinRecreation', 'XWaveName',
        'ContourNameToWaveRef', 'CsrWaveRef', 'CsrXWaveRef',
        'ImageNameToWaveRef', 'NewFreeWave', 'TagWaveRef', 'TraceNameToWaveRef',
        'WaveRefIndexed', 'XWaveRefFromTrace', 'GetDataFolderDFR',
        'GetWavesDataFolderDFR', 'NewFreeDataFolder', 'ThreadGroupGetDFR',
    )

    tokens = {
        'root': [
            (r'//.*$', Comment.Single),
            (r'"([^"\\]|\\.)*"', String),
            # Flow Control.
            (words(flowControl, prefix=r'\b', suffix=r'\b'), Keyword),
            # Types.
            (words(types, prefix=r'\b', suffix=r'\b'), Keyword.Type),
            # Keywords.
            (words(keywords, prefix=r'\b', suffix=r'\b'), Keyword.Reserved),
            # Built-in operations.
            (words(operations, prefix=r'\b', suffix=r'\b'), Name.Class),
            # Built-in functions.
            (words(functions, prefix=r'\b', suffix=r'\b'), Name.Function),
            # Compiler directives.
            (r'^#(include|pragma|define|ifdef|ifndef|endif)',
             Name.Decorator),
            (r'[^a-z"/]+$', Text),
            (r'.', Text),
        ],
    }
