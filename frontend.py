from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, FileResponse
from pathlib import Path
import modal
import tempfile
import ffmpeg
import requests

# -------------------
# Modal setup
# -------------------
app_modal = modal.App("cpr-video-generator")
here = Path(__file__).parent

MODAL_FINETUNE_ID = "nova_2025-11-08 21:12:58.543332"  # replace with your finetune id
generator_cls = modal.Cls.from_name("finetune-video-generate", "VideoGenerator")

# -------------------
# FastAPI setup
# -------------------
app = FastAPI()

SCENARIOS = [
    "User stuck under a pillar, CPR being administered",
    "User in a wheelchair, emergency CPR scenario",
    "User collapsed on stairs, CPR being performed",
    "User trapped under a table, CPR simulation",
]

TASK_SETTING = [
    "Safe",
    "Hazardous - Hazmat",
    "Hazardous - Violence threat",
    "Hazardous - Traffic active roadway",
    "Hazardous - Unstable surfaces",
    "Hazardous - Severe weather",
    "Hazardous - Confined space",
    "Hazardous - Height / elevated",
    "Hazardous - Entrapped / pinned / crushed",
]

TASK_COMPLEXITY = [
    "Pediatric",
    "Geriatric",
    "Bariatric",
    "Pregnant",
    "Clear history",
    "Poor historian (altered)",
    "Poor historian (language barrier)",
    "Straightforward symptom presentation",
    "Atypical symptom presentation",
    "Symptom red herrings",
    "Unusual patient positioning"
]

COGNITIVE_LOAD = [
    "Bystander none",
    "Bystander helpful",
    "Bystander obstructive",
    "Single patient",
    "Multiple patients",
    "Mass casualty",
    "Resources full",
    "Resources limited",
    "Resources austere"
]


LAST_SCENARIO_PATH = here / "medical_prompts.txt"

# -------------------
# HTML template with floating "trAIn" title
# -------------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>trAIn</title>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600&display=swap" rel="stylesheet">
    <style>
        body {{
            font-family: 'Space Grotesk', 'Helvetica', 'Arial', sans-serif;
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            background: linear-gradient(135deg, #1f2b38, #223944, #2f5556, #37424a);
            color: #f0f0f0;
        }}
        .title {{
            font-size: 120px;
            letter-spacing: 4px;
            font-weight: 900;
            margin: 80px 0 30px 0;
            display: flex;
            justify-content: center;
            gap: 14px;
        }}

        .letter {{
            display: inline-block;
            animation: floatLetter 3.2s ease-in-out infinite;
        }}

        .letter:nth-child(1) {{ animation-delay: 0s; }}
        .letter:nth-child(2) {{ animation-delay: 0.3s; }}
        .letter:nth-child(3) {{ animation-delay: 0.6s; }}
        .letter:nth-child(4) {{ animation-delay: 0.9s; }}
        .letter:nth-child(5) {{ animation-delay: 1.2s; }}

        .ai {{
            color: #ffb74d;
        }}

        @keyframes floatLetter {{
            0%,100% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-10px); }}
        }}

        .container {{
            ground: rgba(255, 255, 255back, 0.05);
            backdrop-filter: blur(12px);
            border-radius: 24px;
            padding: 70px;
            max-width: 720px;
            width: 90%;
            text-align: center;
            justify-content: center;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            margin-bottom: 40px;
        }}
        h2 {{
            color: #f8f8f8;
            margin-bottom: 25px;
            font-weight: 600;
        }}
        p {{
            font-size: 17px;
            line-height: 1.8;
            margin-bottom: 20px;
        }}
        video {{
            border-radius: 14px;
            max-width: 100%;
            margin: 25px 0;
            box-shadow: 0 6px 20px rgba(0,0,0,0.25);
        }}
        input[type="text"] {{
            width: 100%;
            padding: 16px;
            margin: 15px 0;
            border-radius: 14px;
            border: none;
            font-size: 16px;
        }}
        input[type="submit"], a.button {{
            background: linear-gradient(135deg, #a35f7d, #ff914d);
            color: white;
            padding: 16px 32px;
            border: none;
            border-radius: 14px;
            cursor: pointer;
            font-size: 16px;
            text-decoration: none;
            transition: 0.3s;
        }}
        input[type="submit"]:hover, a.button:hover {{
            filter: brightness(1.2);
        }}
        .actions {{
            margin-top: 25px;
            display: flex;
            justify-content: center;
            gap: 20px;
            flex-wrap: wrap;
        }}
        form {{
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="title">
    <span class="letter">t</span>
    <span class="letter">r</span>
    <span class="letter ai">A</span>
    <span class="letter ai">I</span>
    <span class="letter">n</span>
</div>

    <div class="container">
        {body_content}
    </div>
</body>
</html>
"""

# -------------------
# Routes
# -------------------
@app.get("/", response_class=HTMLResponse)
def index():
    ts_html = "".join([f"<option value='{s}'>{s}</option>" for s in TASK_SETTING])
    tc_html = "".join([f"<option value='{s}'>{s}</option>" for s in TASK_COMPLEXITY])
    cl_html = "".join([f"<option value='{s}'>{s}</option>" for s in COGNITIVE_LOAD])

    body = f"""
        <form action="/generate_scenario" method="post">
            <h2>Task Setting</h2>
            <select name="task_setting" style="padding:14px; border-radius:14px; width:100%; font-size:16px;">
                {ts_html}
            </select>
            <br><br>

            <h2>Task Complexity</h2>
            <select name="task_complexity" style="padding:14px; border-radius:14px; width:100%; font-size:16px;">
                {tc_html}
            </select>
            <br><br>

            <h2>Cognitive Load / Multiple Actors</h2>
            <select name="cognitive_load" style="padding:14px; border-radius:14px; width:100%; font-size:16px;">
                {cl_html}
            </select>

            <br><br><br>
            <input type="submit" value="Generate Scenario">
        </form>
    """
    return HTML_TEMPLATE.format(body_content=body)



@app.post("/generate_scenario", response_class=HTMLResponse)
def generate_scenario(task_setting: str = Form(...), task_complexity: str = Form(...), cognitive_load: str = Form(...)):
    prompt = f"CPR emergency scenario. Task setting: {task_setting}. Task complexity: {task_complexity}. Cognitive load: {cognitive_load}. Generate a visual CPR simulation demonstrating the setting clearly."
    LAST_SCENARIO_PATH.write_text(prompt)

    # generator = generator_cls(finetune_id=MODAL_FINETUNE_ID)

    # Call without custom prompt file (uses default)
    response = requests.get(
        "https://elizabetht1--medical-video-generator-main-dev.modal.run/",
        params={"finetune_id": MODAL_FINETUNE_ID}
    )

    # Save the video
    scenario_path = here / "scenario.mp4"
    with open(scenario_path, "wb") as f:
        f.write(response.content)

    body = f"""
        <h2>Generated Scenario:</h2>
        <p><b>{prompt}</b></p>
        <video controls>
            <source src="/scenario_video" type="video/mp4">
        </video>
        <form action="/generate_user_action" method="post">
            <label for="action">What would you do next?</label><br>
            <input type="text" id="action" name="action" placeholder="Describe your action"><br>
            <input type="submit" value="Submit">
        </form>
        <div class="actions">
            <a class="button" href="/">Go back</a>
        </div>
    """
    return HTML_TEMPLATE.format(body_content=body)


@app.get("/scenario_video")
def scenario_video():
    scenario_path = here / "scenario.mp4"
    return FileResponse(scenario_path, media_type="video/mp4")


@app.post("/generate_user_action", response_class=HTMLResponse)
def generate_user_action(action: str = Form(...)):
    scenario_path = here / "scenario.mp4"
    if not scenario_path.exists():
        return "Stage 1 video not found. Generate scenario first."

    scenario_text = LAST_SCENARIO_PATH.read_text() if LAST_SCENARIO_PATH.exists() else "Previous scenario"

    new_prompt = f"Previous scenario: {scenario_text}. Now, user action: {action}."

    generator = generator_cls(finetune_id=MODAL_FINETUNE_ID)
    continuation_bytes = generator.run(new_prompt, num_frames=75)

    continuation_path = here / "continuation.mp4"
    continuation_path.write_bytes(continuation_bytes)

    with tempfile.TemporaryDirectory() as tmpdir:
        last_frame_path = Path(tmpdir) / "last_frame.mp4"
        ffmpeg.input(str(scenario_path), ss="00:00:04", t=1).output(
            str(last_frame_path), vcodec="libx264", acodec="aac", r=15
        ).run(overwrite_output=True)

        final_output_path = here / "final_video.mp4"
        ffmpeg.input(str(last_frame_path)).concat(
            ffmpeg.input(str(continuation_path)), v=1, a=0
        ).output(str(final_output_path), vcodec="libx264", acodec="aac", r=15).run(overwrite_output=True)

    body = f"""
        <h2>Previous Scenario:</h2>
        <p><b>{scenario_text}</b></p>
        <h2>Your Action:</h2>
        <p><b>{action}</b></p>
        <video controls>
            <source src="/final_video" type="video/mp4">
        </video>
        <div class="actions">
            <a class="button" href="/">Go back</a>
            <a class="button" href="/generate_scenario">Generate new scenario</a>
        </div>
    """
    return HTML_TEMPLATE.format(body_content=body)


@app.get("/final_video")
def final_video():
    final_output_path = here / "final_video.mp4"
    return FileResponse(final_output_path, media_type="video/mp4")