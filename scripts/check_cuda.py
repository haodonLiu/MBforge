"""Check if RapidOCR is actually using CUDA."""
import time
import numpy as np
from PIL import Image, ImageDraw
from rapidocr import RapidOCR, EngineType, LangDet, LangRec, ModelType, OCRVersion

engine = RapidOCR(
    params={
        "Det.engine_type": EngineType.ONNXRUNTIME,
        "Det.lang_type": LangDet.EN,
        "Det.model_type": ModelType.MEDIUM,
        "Det.ocr_version": OCRVersion.PPOCRV6,
        "Det.providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
        "Rec.engine_type": EngineType.ONNXRUNTIME,
        "Rec.lang_type": LangRec.EN,
        "Rec.model_type": ModelType.MEDIUM,
        "Rec.ocr_version": OCRVersion.PPOCRV6,
        "Rec.providers": ["CUDAExecutionProvider", "CPUExecutionProvider"],
    }
)

# Create test image with text
img = Image.new("RGB", (400, 100), "white")
draw = ImageDraw.Draw(img)
draw.text((10, 30), "Hello World Test 123 ABC", fill="black")
arr = np.array(img)

# Warmup
engine(arr)

# Time 5 runs
times = []
for _ in range(5):
    t0 = time.perf_counter()
    engine(arr)
    times.append(time.perf_counter() - t0)

print(f"Test image inference (5 runs): {[f'{t*1000:.1f}ms' for t in times]}")
print(f"Average: {sum(times)/len(times)*1000:.1f}ms")

# Check GPU usage
import onnxruntime as ort
print(f"\nAvailable providers: {ort.get_available_providers()}")

# Check if CUDA is actually being used by monitoring
try:
    import subprocess
    result = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", "--format=csv,noheader"],
                          capture_output=True, text=True, timeout=5)
    print(f"\nGPU status: {result.stdout.strip()}")
except Exception as e:
    print(f"nvidia-smi check failed: {e}")
