import random
from pathlib import Path

import modal


app = modal.App("medical-video-generator")

here = Path(__file__).parent

image = modal.Image.debian_slim().pip_install("fastapi[standard]")


@app.function(image=image)
@modal.fastapi_endpoint()
def main(finetune_id, prompt_file=None):
    clip_duration = 10  # seconds

    generator = modal.Cls.from_name("finetune-video-generate", "VideoGenerator")(
        finetune_id=finetune_id
    )

    if prompt_file is None:
        prompt_file = here / "data" / "medical_prompts.txt"

    # prompts = Path(prompt_file).read_text().splitlines()
    # print(f"loaded prompt file: {prompt_file}")

    prompts = [
    "[trigger] Safe outdoor park setting with open space and good lighting",
    "[trigger] Young child lying unresponsive on the ground, approximately 6-8 years old",
    "[trigger] Responder kneeling beside child, checking for responsiveness by tapping shoulders",
    "[trigger] Responder tilting child's head back slightly to open airway and checking for breathing",
    "[trigger] Responder calling for help while maintaining position next to child",
    "[trigger] Responder positioning hands on center of child's chest for compressions",
    "[trigger] Responder performing chest compressions with proper hand placement and depth",
    "[trigger] Responder giving rescue breaths after compression cycle, pinching nose and sealing mouth",
    "[trigger] Responder continuing compression cycles with visible rhythmic motion",
    "[trigger] Responder maintaining CPR while emergency services arrive in background"
    ]
    # generate video clips
    videos_bytes = list(
        generator.run.map(
            prompts, kwargs={"num_frames": 15 * clip_duration}, order_outputs=False
        )
    )
    video = combine.remote(videos_bytes)

    # Optional: save locally for debugging
    output_dir = Path("/tmp") / finetune_id
    output_dir.mkdir(exist_ok=True, parents=True)
    output_path = output_dir / "video.mp4"
    output_path.write_bytes(video)
    print(f"output written to {output_path}")
    
    # Return video bytes as response
    from fastapi.responses import Response
    return Response(content=video, media_type="video/mp4")

# @app.local_entrypoint()
# def main(finetune_id, prompt_file=None):
#     clip_duration = 10  # seconds

#     generator = modal.Cls.from_name("finetune-video-generate", "VideoGenerator")(
#         finetune_id=finetune_id
#     )

 
#     if prompt_file is None:
#         prompt_file = here / "data" / "medical_prompts.txt"

#     # load prompt file
#     prompts = Path(prompt_file).read_text().splitlines()
#     print(f"loaded prompt file: {prompt_file}")

  

#     # n_clips = (total_duration // clip_duration) + (total_duration % clip_duration != 0)

#     # generate video clips
#     videos_bytes = list(
#         generator.run.map(
#             prompts, kwargs={"num_frames": 15 * clip_duration}, order_outputs=False
#         )
#     )
#     video = combine.remote(videos_bytes)

#     # save locally
#     output_dir = Path("/tmp") / finetune_id
#     output_dir.mkdir(exist_ok=True, parents=True)
#     # mp3_name = mp3_file.stem
#     output_path = output_dir / "video.mp4"

#     output_path.write_bytes(video)
#     print(f"output written to {output_path}")



@app.function(image=modal.Image.debian_slim().pip_install("mutagen"))
def get_duration(mp3: bytes) -> int:
    from io import BytesIO

    from mutagen.mp3 import MP3

    audio = MP3(BytesIO(mp3))

    return audio.info.length


@app.function(
    image=modal.Image.debian_slim().apt_install("ffmpeg").pip_install("ffmpeg-python")
)
def combine(videos: list[bytes]) -> bytes:
    import tempfile

    import ffmpeg

    with tempfile.TemporaryDirectory() as tmpdir:
        # write out video inputs to files
        video_paths = []
        for i, chunk in enumerate(videos):
            path = Path(tmpdir) / f"chunk{i}.mp4"
            path.write_bytes(chunk)
            video_paths.append(path)

        # concatenate video inputs together
        video_inputs = [ffmpeg.input(video_path) for video_path in video_paths]
        video_concat = ffmpeg.concat(*video_inputs, v=1, a=0).node

        # write audio to file
        # audio_path = Path(tmpdir) / "audio.mp3"
        # audio_path.write_bytes(audio)

        # combine audio with concatenated video
        # audio_input = ffmpeg.input(str(audio_path))
        output_path = Path(tmpdir) / "output.mp4"
        output = ffmpeg.output(
            video_concat[0],
            str(output_path),
            vcodec="libx264",
            acodec="aac",
            shortest=None,
        )

        # execute pipeline
        output.run()

        return output_path.read_bytes()
