"""Builds series/experiment.json episodes 2-15 from shot lists.
Character descriptions are inserted verbatim every time so Veo keeps faces and outfits consistent.
Run: python series/build_experiment.py
"""
import json
from pathlib import Path

P = Path(__file__).parent / "experiment.json"

C = {
    "NIKA": "a handsome lean young Georgian man with styled dark wavy hair and light stubble in a fitted black leather jacket over a white crewneck",
    "SALOME": "a beautiful slim young Georgian woman with long glossy light-brown waves, natural glam makeup, gold hoops and a cream cropped knit cardigan",
    "DATO": "a fit, handsome Georgian man with a short faded haircut and defined jaw in a fitted black hoodie and silver watch",
    "LIZI": "a pretty petite Georgian woman with a sleek black bob and thin gold round glasses in an oversized olive blazer over a white top",
    "GUGA": "a charming lean Georgian man with curly auburn hair and a warm smile in a mustard knit sweater",
    "TEKLA": "a striking Georgian woman with sharp features and dark hair in a sleek tight bun in a fitted charcoal hoodie",
    "SPEAKER": "a calm, deep, slightly distorted male voice from the black wall speaker",
    "ANA": "a beautiful young Georgian woman with long straight dark hair and pale skin in a white turtleneck",
}
HEAD = ("15-second fast-paced cinematic sequence, vertical 9:16, realistic, 35mm film look, film grain, "
        "{light}, quick cuts, no dead time. Setting: an isolated modern-rustic wooden cabin in a dark pine forest.")
FOOT = ("Characters are fashionable and good-looking. Natural lip movement. Ambient: {amb}. "
        "No subtitles, no text on screen.")


FEMALE = {"SALOME", "LIZI", "TEKLA", "ANA"}


def fill(text):
    """First mention of a character in a shot = full description, later mentions = he/she."""
    import re
    seen = set()

    def sub(m):
        k = m.group(1)
        if k == "SPEAKER" or k not in seen:
            seen.add(k)
            return C[k]
        start = m.start() == 0 or text[:m.start()].rstrip().endswith((".", "!", "?", ":"))
        pron = "she" if k in FEMALE else "he"
        return pron.capitalize() if start else pron
    return re.sub(r"\{([A-Z]+)\}", sub, text)


NARRATOR = "a deep, calm male narrator voice-over (not on screen)"


def clip(shots, lines, light="cold blue tones", amb="wind, creaking wood", pops=None):
    times = [(0, 4), (4, 8), (8, 11), (11, 15)] if len(shots) == 4 else [(0, 5), (5, 10), (10, 15)]
    # Veo speaks the narrator itself (in sync, same mix); put each line into the shot it belongs to
    shots, out = list(shots), []
    for line in lines:
        if line["who"] != "narrator":
            out.append(line)
            continue
        idx = max(i for i, (a, b) in enumerate(times) if a <= line["at"] + 0.01)
        a, b = times[idx]
        text = line["text"].replace("*", "")
        shots[idx] = shots[idx].replace("No dialogue.", "").rstrip() + f' {NARRATOR.capitalize()} says slowly in Georgian: "{text}"'
        out.append({"who": "veo", "from": a + 0.2, "to": b - 0.1, "text": line["text"]})
    lines = out
    body = "\n".join(f"Shot {i + 1} ({a}-{b}s): {fill(s)}" for i, ((a, b), s) in enumerate(zip(times, shots)))
    prompt = HEAD.format(light=light) + "\n" + body + "\n" + FOOT.format(amb=amb)
    return {"prompt": prompt, "lines": lines, "pops": pops or []}


def N(at, text):
    return {"who": "narrator", "at": at, "text": text}


def V(a, b, text):
    return {"who": "veo", "from": a, "to": b, "text": text}


def say(who, line, how=""):
    return f'{{{who}}} says in Georgian{(" " + how) if how else ""}: "{line}"'


EP = []

# 2 ------------------------------------------------------------------
EP.append({"n": 2, "title": "პირველი კენჭისყრა", "next": "🔒 სერია 3 · ორ დღეში",
           "caption": "გუგა უდანაშაულო იყო... მაშ, ვინ? 👇", "clips": [
    clip(["Morning in the cabin kitchen, the six eat breakfast in tense silence, suspicious side glances. No dialogue.",
          f"{{DATO}} slams his mug on the table and points across it at a woman. " + say("DATO", "შენ საიდან იცოდი ჩემი სახელი?", "angrily"),
          f"{{SALOME}} raises an eyebrow, calm and sarcastic. " + say("SALOME", "შენ ყველა გიცნობს, დათო."),
          f"Dim corridor: {{TEKLA}} leans close to {{LIZI}} and whispers, glancing toward the kitchen. " + say("TEKLA", "გუგა ზედმეტად მშვიდია. არ მომწონს.", "in a quiet whisper")],
         [N(0.3, "პირველი დილა. და *პირველი ეჭვი*."), V(4.3, 7.8, "შენ საიდან იცოდი *ჩემი სახელი*?"),
          V(8.2, 10.8, "შენ ყველა გიცნობს, დათო."), V(11.2, 14.7, "გუგა *ზედმეტად მშვიდია*. არ მომწონს.")]),
    clip(["Evening, living room by candlelight: each of the six drops a folded paper vote into a glass bowl, close-ups of hands. No dialogue.",
          f"The wall speaker crackles; everyone stares up. {{SPEAKER}} says in Georgian: \"ყველაზე მეტი ხმა — გუგა. ის მოღალატე არ იყო.\"",
          f"{{GUGA}} stands up, forcing a smile, walks down a dark hallway into a door glowing deep red, looks back once; the red door shuts with a heavy thud. No dialogue.",
          f"Night, a bedroom: {{NIKA}} lifts his pillow and finds a folded note, unfolds it, his face drains of color. No dialogue."],
         [N(0.3, "საღამოს — *პირველი კენჭისყრა*."), V(4.3, 7.9, "ყველაზე მეტი ხმა — გუგა. ის *მოღალატე არ იყო*."),
          N(11.2, "ბალიშის ქვეშ წერილი იდო: *შემდეგი შენ ხარ*.")],
         amb="static crackle, heavy door thud, wind")]})

# 3 ------------------------------------------------------------------
EP.append({"n": 3, "title": "სარკის უკან", "next": "🔒 სერია 4 · ორ დღეში",
           "caption": "ვინ მისცა სალომეს დათოს საიდუმლო? 👇", "clips": [
    clip([f"Bathroom at dawn: {{LIZI}} wipes the fogged mirror and notices a tiny red light blinking behind the glass.",
          f"{{LIZI}} runs into the hallway to {{NIKA}}. " + say("LIZI", "სარკის უკან კამერაა!", "in a frightened whisper"),
          f"Kitchen: {{TEKLA}} calmly pours coffee, not reacting at all, watching them over her cup. No dialogue.",
          f"Living room: {{SALOME}} throws a thin paper folder on the table in front of everyone. " + say("SALOME", "დათო ოცდაათი ათასით ვალშია.")],
         [V(4.3, 7.8, "სარკის უკან *კამერაა*!"), N(8.2, "თეკლას *არ გაჰკვირვებია*."),
          V(11.3, 14.6, "დათო ოცდაათი ათასით *ვალშია*.")],
         amb="dripping water, wind"),
    clip([f"{{DATO}} grabs {{SALOME}} by the wrist, furious, close faces. " + say("DATO", "ვინ მოგცა ეს?!", "through his teeth"),
          f"{{SALOME}} pulls her arm free, unafraid. " + say("SALOME", "ჩემს ოთახში დამხვდა. კარის ქვეშ."),
          f"Close-up of {{TEKLA}} in the background, the faintest smile. No dialogue.",
          f"The wall speaker crackles. {{SPEAKER}} says in Georgian: \"ამაღამ კენჭისყრაა.\" Everyone looks at {{DATO}}."],
         [V(0.4, 3.8, "ვინ მოგცა *ეს*?!"), V(4.3, 7.8, "ჩემს ოთახში დამხვდა. *კარის ქვეშ*."),
          N(8.1, "ვიღაც მათ ერთმანეთზე *აქეზებს*."), V(11.3, 14.0, "ამაღამ *კენჭისყრაა*.")],
         amb="tense silence, static crackle")]})

# 4 ------------------------------------------------------------------
EP.append({"n": 4, "title": "მეორე ღამე", "next": "🔒 სერია 5 · ორ დღეში",
           "caption": "ვინ იყვირა სარდაფში? 👇", "clips": [
    clip([f"Night, {{TEKLA}} quietly speaks to {{LIZI}} in a dim corridor. " + say("TEKLA", "ვალიანი კაცი ყველაფერს გააკეთებს ფულისთვის.", "softly"),
          "Votes dropping into the glass bowl, slow motion, candlelight. No dialogue.",
          f"The speaker crackles. {{SPEAKER}} says in Georgian: \"დათო.\"",
          f"{{DATO}} jumps up, desperate, shouting at everyone. " + say("DATO", "მე არ ვარ! გესმით?!")],
         [V(0.4, 4.6, "ვალიანი კაცი *ყველაფერს* გააკეთებს ფულისთვის."), N(5.1, "თეკლამ სიტყვა *ზუსტად* ჩააგდო."),
          V(8.3, 10.6, "დათო."), V(11.3, 14.6, "მე *არ ვარ*! გესმით?!")]),
    clip([f"{{DATO}} walks into the red-lit hallway, looking back with anger, the red door closes. No dialogue.",
          f"The speaker crackles. {{SPEAKER}} says in Georgian: \"შეცდით. ისევ.\"",
          "Sudden blackout: the lamps die, total darkness, only moonlight through windows; silhouettes freeze. No dialogue.",
          "From below the floor, a muffled woman's scream echoes; flashlights snap on, pointing at a basement door. No dialogue."],
         [N(0.4, "დათოც *უდანაშაულო* აღმოჩნდა."), V(4.4, 7.6, "შეცდით. *ისევ*."),
          N(8.2, "და მერე... *შუქი ჩაქრა*.")],
         light="red light then total darkness", amb="door thud, electric buzz cutting out, distant scream")]})

# 5 ------------------------------------------------------------------
EP.append({"n": 5, "title": "სარდაფი", "next": "🔒 სერია 6 · ორ დღეში",
           "caption": "ვინ არის ანა? 👇", "clips": [
    clip([f"{{NIKA}} and {{LIZI}} creep down narrow wooden basement stairs with flashlights, dust in the beams. No dialogue.",
          "The flashlight reveals a seventh neatly made bed in the corner, with a hospital-like bracelet on the pillow. No dialogue.",
          f"{{LIZI}} picks up the bracelet and reads it. " + say("LIZI", "მონაწილე ნომერი შვიდი...", "in a whisper"),
          f"{{NIKA}} pulls a white hoodie from under the bed; inside the collar a name is stitched. His hands start shaking. No dialogue."],
         [N(0.3, "ხმა *სარდაფიდან* მოდიოდა."), N(4.3, "იქ *მეშვიდე საწოლი* იდგა."),
          V(8.3, 10.8, "მონაწილე *ნომერი შვიდი*...")],
         light="flashlight beams in darkness", amb="creaking stairs, dripping water, heavy breathing"),
    clip([f"Extreme close-up of {{NIKA}}'s eyes filling with tears. " + say("NIKA", "ეს ანას ქურთუკია.", "barely audible"),
          f"{{LIZI}} stares at him, confused. " + say("LIZI", "ვინ არის ანა?"),
          f"{{NIKA}} slowly looks up from the hoodie at her. " + say("NIKA", "ჩემი და. სამი წლის წინ აქ გაქრა."),
          f"At the top of the stairs, half in shadow, {{SALOME}} silently listens, then steps back out of sight. No dialogue."],
         [V(0.4, 3.8, "ეს *ანას* ქურთუკია."), V(4.4, 7.4, "ვინ არის ანა?"),
          V(8.2, 10.9, "ჩემი და. სამი წლის წინ *აქ გაქრა*."), N(11.4, "მაგრამ ამას *სხვაც* ისმენდა.")],
         light="flashlight beams in darkness", amb="dripping water, quiet breathing")]})

# 6 ------------------------------------------------------------------
EP.append({"n": 6, "title": "ანას ჩანაწერი", "next": "🔒 სერია 7 · ორ დღეში",
           "caption": "ანა რას გულისხმობდა? 👇", "clips": [
    clip([f"Flashback, warm grainy home-video look: {{ANA}} laughs into a phone camera in a sunny Tbilisi apartment. No dialogue.",
          f"Flashback, same phone video, night, {{ANA}} now pale and scared in a dark wooden room, whispering into the camera. " + say("ANA", "თუ ამას უყურებ, მე ვერ დავბრუნდი.", "terrified"),
          f"Present: {{NIKA}} sits on the basement floor watching the video on an old phone he found in the hoodie pocket. No dialogue.",
          f"On the phone screen {{ANA}} leans closer and whispers in Georgian: \"არავის ენდო. განსაკუთრებით მას, ვინც მშვიდია.\""],
         [N(0.3, "ქურთუკის ჯიბეში *ძველი ტელეფონი* იყო."), V(4.4, 7.8, "თუ ამას უყურებ, მე *ვერ დავბრუნდი*."),
          V(11.2, 14.7, "არავის ენდო. განსაკუთრებით მას, *ვინც მშვიდია*.")],
         light="warm home video then cold dark", amb="phone audio hiss, distant wind"),
    clip([f"{{NIKA}} lowers the phone and slowly lifts his eyes. No dialogue.",
          f"Quick cuts of everyone upstairs: {{SALOME}} nervously biting her nail, {{LIZI}} pacing, {{TEKLA}} reading a book completely calm. No dialogue.",
          f"Close-up: {{TEKLA}} turns a page and, without looking up, says in Georgian: \"რაღაც იპოვე, ნიკა?\"",
          f"{{NIKA}} freezes at the bottom of the stairs, hiding the phone behind his back. No dialogue."],
         [N(0.3, "ვინ არის აქ *ყველაზე მშვიდი*?"), V(8.3, 10.9, "რაღაც იპოვე, *ნიკა*?"),
          N(11.4, "ნიკამ პირველად იგრძნო *შიში*.")],
         amb="clock ticking, page turning")]})

# 7 ------------------------------------------------------------------
EP.append({"n": 7, "title": "შანტაჟი", "next": "🔒 სერია 8 · ორ დღეში",
           "caption": "ნიკამ სწორი გადაწყვეტილება მიიღო? 👇", "clips": [
    clip([f"Night, a narrow hallway: {{SALOME}} blocks {{NIKA}}'s way, arms crossed. " + say("SALOME", "ყველაფერი გავიგე. შენი და, სარდაფი."),
          f"{{NIKA}} tries to walk past; she steps in front of him again. " + say("NIKA", "რა გინდა?", "coldly"),
          f"{{SALOME}} leans in, whispering. " + say("SALOME", "ამაღამ ჩემთან ერთად მისცემ ხმას."),
          f"{{SALOME}} smiles. " + say("SALOME", "თორემ ყველა გაიგებს, რომ შენ აქ შემთხვევით არ ხარ.")],
         [V(0.4, 3.8, "ყველაფერი გავიგე. *შენი და*, სარდაფი."), V(4.4, 7.4, "რა გინდა?"),
          V(8.2, 10.9, "ამაღამ *ჩემთან ერთად* მისცემ ხმას."), V(11.2, 14.7, "თორემ ყველა გაიგებს, რომ შენ აქ *შემთხვევით არ ხარ*.")]),
    clip([f"{{NIKA}} looks away, jaw clenched, then gives a small nod. No dialogue.",
          f"Living room, the remaining four sit facing each other: {{NIKA}}, {{SALOME}}, {{LIZI}}, {{TEKLA}}. No dialogue.",
          f"The speaker crackles. {{SPEAKER}} says in Georgian: \"ახალი წესი. ამაღამ ხმას მოღალატეც აძლევს.\"",
          f"Slow push-in on {{TEKLA}}'s calm face, the corner of her mouth lifting. No dialogue."],
         [N(0.3, "ნიკა *დათანხმდა*."), N(4.4, "დარჩა *ოთხი*."),
          V(8.3, 14.0, "ახალი წესი. ამაღამ ხმას *მოღალატეც* აძლევს.")],
         amb="static crackle, fire crackling")]})

# 8 ------------------------------------------------------------------
EP.append({"n": 8, "title": "ლიზი", "next": "🔒 სერია 9 · ორ დღეში",
           "caption": "რა უთხრა ლიზიმ ნიკას? 👇", "clips": [
    clip(["Votes dropping into the glass bowl, slow motion; close-up of a paper with the name ლიზი written on it. No dialogue.",
          f"The speaker crackles. {{SPEAKER}} says in Georgian: \"ლიზი.\"",
          f"{{LIZI}} looks at {{NIKA}} with hurt eyes. " + say("LIZI", "შენც ჩემზე მიეცი ხმა?", "quietly"),
          f"{{NIKA}} cannot meet her gaze; {{SALOME}} beside him looks satisfied. No dialogue."],
         [N(0.3, "ხმები *დაითვალეს*."), V(4.4, 7.4, "ლიზი."),
          V(8.3, 10.9, "შენც *ჩემზე* მიეცი ხმა?"), N(11.3, "ნიკამ ვერაფერი *უპასუხა*.")]),
    clip([f"At the red door, {{LIZI}} suddenly hugs {{NIKA}} and whispers into his ear. " + say("LIZI", "თეკლას ოთახში კამერა ჩართული იყო.", "urgently whispering"),
          f"{{LIZI}} steps through the red door; it closes. {{NIKA}} stays staring at it. No dialogue.",
          f"Night, {{NIKA}} quietly pushes open the door to {{TEKLA}}'s dark empty bedroom. No dialogue.",
          "A close-up of a laptop under the bed, its screen glowing with a live grid of camera feeds of every room. No dialogue."],
         [V(0.4, 3.8, "თეკლას ოთახში *კამერა* ჩართული იყო."), N(4.4, "ლიზიც უდანაშაულო იყო."),
          N(11.3, "ეკრანზე *მთელი სახლი* ჩანდა.")],
         light="red light, then dark bedroom", amb="heavy door thud, laptop fan hum")]})

# 9 ------------------------------------------------------------------
EP.append({"n": 9, "title": "ყურსასმენი", "next": "🔒 სერია 10 · ორ დღეში",
           "caption": "ნიკა გაიქცა თუ დარჩა? 👇", "clips": [
    clip([f"{{NIKA}} kneels by the bed, scrolling through the camera feeds on the laptop, his face lit by the screen. No dialogue.",
          "Close-up of the screen: a folder named ანა, with a video thumbnail of a young woman in a white turtleneck. No dialogue.",
          f"{{NIKA}} finds a tiny wireless earpiece next to the laptop and holds it up to the light. No dialogue.",
          f"The bedroom door creaks. {{TEKLA}} stands in the doorway, perfectly calm. " + say("TEKLA", "რამე დაკარგე, ნიკა?")],
         [N(0.3, "თეკლას ლეპტოპში *ყველა კამერა* იყო."), N(4.4, "და საქაღალდე *ანას სახელით*."),
          N(8.2, "და *ყურსასმენი*."), V(11.3, 14.6, "რამე *დაკარგე*, ნიკა?")],
         light="laptop glow in darkness", amb="laptop hum, creaking door"),
    clip([f"{{NIKA}} slowly stands, hiding the earpiece in his fist. " + say("NIKA", "სწორედ შენ გეძებდი.", "tense"),
          f"{{TEKLA}} steps closer, unblinking. " + say("TEKLA", "ზოგი რამის ცოდნა საშიშია."),
          f"She walks past him, closes the laptop with one finger and leaves. No dialogue.",
          f"Close-up of {{NIKA}}'s open hand: the earpiece in his palm crackles and a tiny distorted male voice says in Georgian: \"თეკლა, მიჰყევი გეგმას.\""],
         [V(0.4, 3.8, "სწორედ *შენ* გეძებდი."), V(4.4, 7.8, "ზოგი რამის ცოდნა *საშიშია*."),
          V(11.3, 14.7, "თეკლა, *მიჰყევი გეგმას*.")],
         amb="heartbeat, faint radio crackle")]})

# 10 -----------------------------------------------------------------
EP.append({"n": 10, "title": "ორი ეჭვმიტანილი", "next": "🔒 სერია 11 · ორ დღეში",
           "caption": "სალომე ნიკას ენდობა? 👇", "clips": [
    clip([f"Morning, living room, only three remain: {{NIKA}}, {{SALOME}}, {{TEKLA}}. Cold light. No dialogue.",
          f"{{TEKLA}} suddenly throws the white hoodie with the stitched name onto the table. " + say("TEKLA", "ნიკამ ეს დამალა."),
          f"{{SALOME}} turns to {{NIKA}}, shocked. " + say("SALOME", "შენ თავიდანვე გვატყუებდი?"),
          f"{{NIKA}} raises his hands. " + say("NIKA", "მისმინე. მოღალატე თეკლაა.")],
         [N(0.3, "დარჩა *სამი*."), V(4.4, 7.4, "ნიკამ ეს *დამალა*."),
          V(8.3, 10.9, "შენ თავიდანვე *გვატყუებდი*?"), V(11.3, 14.6, "მისმინე. მოღალატე *თეკლაა*.")]),
    clip([f"{{TEKLA}} laughs softly, looking at {{SALOME}}. " + say("TEKLA", "მას ახლა ყველაფერს ეტყვის."),
          f"{{SALOME}} looks back and forth between them, torn, breathing fast. No dialogue.",
          f"{{SALOME}} steps away from {{NIKA}}. " + say("SALOME", "ამაღამ შენ გაძლევ ხმას, ნიკა.", "coldly"),
          f"Close-up of {{NIKA}}'s hand slipping into his pocket and touching the earpiece. No dialogue."],
         [V(0.4, 3.8, "მას ახლა *ყველაფერს* ეტყვის."), N(4.4, "სალომე *ორს შორის* დარჩა."),
          V(8.3, 10.9, "ამაღამ *შენ* გაძლევ ხმას, ნიკა."), N(11.3, "მაგრამ ნიკას *მტკიცებულება* ჰქონდა.")],
         amb="clock ticking, heartbeat")]})

# 11 -----------------------------------------------------------------
EP.append({"n": 11, "title": "ბოლო ღამე", "next": "🔒 სერია 12 · ორ დღეში",
           "caption": "სად გაქრა სალომე? 👇", "clips": [
    clip([f"Night vote: {{SALOME}} raises a paper with ნიკა written on it; {{TEKLA}} raises the same. No dialogue.",
          f"{{NIKA}} stands, holds the earpiece up to the wall speaker microphone and presses it. No dialogue.",
          "From the speaker, a replayed distorted male voice says in Georgian: \"თეკლა, მიჰყევი გეგმას.\"",
          f"{{SALOME}} slowly turns her head to {{TEKLA}}, eyes wide. " + say("SALOME", "შენ...", "in shock")],
         [N(0.3, "ორი ხმა *ნიკას* წინააღმდეგ."), N(4.4, "მაგრამ ნიკამ *ჩანაწერი* ჩართო."),
          V(8.3, 11.0, "თეკლა, *მიჰყევი გეგმას*."), V(11.4, 13.5, "შენ...")],
         amb="static crackle, heartbeat"),
    clip(["All the lights die at once; total darkness, a single gasp. No dialogue.",
          "Five seconds later the lamps flicker back on. No dialogue.",
          f"{{SALOME}}'s chair is empty, still rocking. Her gold hoop earring lies on the floor. No dialogue.",
          f"{{NIKA}} and {{TEKLA}} are alone, staring at each other across the room. " + say("TEKLA", "ახლა მხოლოდ ჩვენ დავრჩით.", "softly")],
         [N(0.3, "და მერე... *სიბნელე*."), N(5.2, "როცა შუქი აინთო..."),
          N(8.2, "სალომე *აღარ იყო*."), V(11.4, 14.6, "ახლა *მხოლოდ ჩვენ* დავრჩით.")],
         light="total darkness, then flickering warm lamps", amb="electric buzz, chair creaking")]})

# 12 -----------------------------------------------------------------
EP.append({"n": 12, "title": "მოღალატე", "next": "🔒 სერია 13 · ორ დღეში",
           "caption": "ვინ გამოიცანით, რომ თეკლა იყო? 👇", "clips": [
    clip([f"{{NIKA}} takes a step toward {{TEKLA}}. " + say("NIKA", "შენ ხარ მოღალატე.", "firmly"),
          f"{{TEKLA}} holds his gaze for a long beat, then nods once. " + say("TEKLA", "კი. მე ვარ."),
          f"Flashback, cold grainy look: {{TEKLA}} three years ago, younger, in this same cabin, sitting next to {{ANA}}, both scared. No dialogue.",
          f"Present: {{TEKLA}} speaks with pain in her eyes. " + say("TEKLA", "მეც მონაწილე ვიყავი. ანასთან ერთად.")],
         [V(0.4, 3.6, "შენ ხარ *მოღალატე*."), V(4.4, 7.4, "კი. *მე ვარ*."),
          N(8.2, "სამი წლის წინ თეკლაც *აქ იყო*."), V(11.3, 14.6, "მეც მონაწილე ვიყავი. *ანასთან ერთად*.")],
         light="warm lamps, then cold flashback"),
    clip([f"{{TEKLA}} sits down slowly. " + say("TEKLA", "ვინც დარჩა, მათთვის იწყებს მუშაობას."),
          f"{{NIKA}} grabs her shoulders. " + say("NIKA", "ანა სად არის?!", "desperate"),
          f"{{TEKLA}} looks him in the eyes. " + say("TEKLA", "შენი და ცოცხალია, ნიკა."),
          "Behind them, deep in the hallway, the red door slowly opens by itself, red light spilling out. No dialogue."],
         [V(0.4, 3.8, "ვინც დარჩა, მათთვის *იწყებს მუშაობას*."), V(4.4, 7.4, "ანა *სად არის*?!"),
          V(8.3, 10.9, "შენი და *ცოცხალია*, ნიკა."), N(11.3, "და წითელი კარი *თავისით გაიღო*.")],
         light="warm lamps with red light from the hallway", amb="heartbeat, door creaking open")]})

# 13 -----------------------------------------------------------------
EP.append({"n": 13, "title": "წითელი ოთახი", "next": "🔒 სერია 14 · ორ დღეში",
           "caption": "ისინი თავიდანვე ყველაფერს უყურებდნენ?! 👇", "clips": [
    clip([f"{{NIKA}} and {{TEKLA}} walk slowly down the red-lit hallway toward the open red door. No dialogue.",
          "They step through: a high-tech control room full of monitors showing every room of the cabin. No dialogue.",
          f"In swivel chairs facing the screens sit {{GUGA}}, {{DATO}}, {{LIZI}} and {{SALOME}}, alive and calm, eating popcorn. No dialogue.",
          f"{{GUGA}} turns around in his chair and waves with a grin. " + say("GUGA", "როგორც იქნა! ჩვენ ყველაფერს ვუყურებდით.")],
         [N(0.3, "წითელი ოთახი *ციხე* არ იყო."), N(4.4, "ეს *სამეთვალყურეო ოთახი* იყო."),
          N(8.2, "და იქ ყველა იჯდა. *ცოცხლები*."), V(11.3, 14.6, "როგორც იქნა! ჩვენ *ყველაფერს* ვუყურებდით.")],
         light="red light, then cold blue monitor glow", amb="electronic hum, monitors beeping"),
    clip([f"{{NIKA}} stares at them in disbelief. " + say("NIKA", "ეს რა არის? თამაშია?", "angry and confused"),
          f"{{LIZI}} answers gently. " + say("LIZI", "ექსპერიმენტი ჩვენ არ ვიყავით, ნიკა."),
          f"{{LIZI}} points at the central screen: a live feed of {{NIKA}} himself, labeled with a red dot. No dialogue.",
          f"{{SALOME}} adds quietly. " + say("SALOME", "ექსპერიმენტი შენ ხარ.")],
         [V(0.4, 3.8, "ეს რა არის? *თამაშია*?"), V(4.4, 7.8, "ექსპერიმენტი *ჩვენ* არ ვიყავით, ნიკა."),
          N(8.2, "ცენტრალურ ეკრანზე *ნიკა* ჩანდა."), V(11.4, 14.2, "ექსპერიმენტი *შენ ხარ*.")],
         light="cold blue monitor glow", amb="electronic hum, heartbeat")]})

# 14 -----------------------------------------------------------------
EP.append({"n": 14, "title": "დოქტორი", "next": "🔒 ფინალი · ორ დღეში",
           "caption": "ამას ელოდით?! 👇", "clips": [
    clip(["All the monitors switch to black at once; the speaker crackles. No dialogue.",
          f"{{SPEAKER}} says in Georgian: \"შენ ერთადერთი იყავი, ვინც არავის უღალატა.\"",
          "A door at the back of the control room slides open; a silhouette in white stands in bright backlight, holding a small voice-changing microphone. No dialogue.",
          f"The silhouette lowers the microphone; the light reveals {{ANA}}. No dialogue."],
         [N(0.3, "ეკრანები *ჩაქრა*."), V(4.4, 7.8, "შენ ერთადერთი იყავი, ვინც *არავის უღალატა*."),
          N(8.2, "„დოქტორი“ *გამოჩნდა*.")],
         light="cold blue, then bright white backlight", amb="electric hum, static, footsteps"),
    clip([f"{{NIKA}} freezes, tears in his eyes. " + say("NIKA", "ანა?..", "barely breathing"),
          f"{{ANA}} smiles softly with a strange calm. " + say("ANA", "გამარჯობა, ძმაო. მე ვარ დოქტორი."),
          f"Close-up of {{NIKA}}'s face, shock turning into anger. No dialogue.",
          f"{{ANA}} steps closer. " + say("ANA", "მინდოდა მენახა, ვის ენდობი.")],
         [V(0.4, 3.6, "ანა?.."), V(4.4, 7.8, "გამარჯობა, ძმაო. *მე ვარ დოქტორი*."),
          N(8.2, "სამი წელი ის *აქ იყო*."), V(11.3, 14.4, "მინდოდა მენახა, *ვის ენდობი*.")],
         light="bright white light in the control room", amb="heartbeat, electronic hum")]})

# 15 -----------------------------------------------------------------
EP.append({"n": 15, "title": "ბოლო წესი", "next": "🔒 სეზონი 2 · მალე",
           "caption": "გინდათ მეორე სეზონი? დაწერე „კი“ 👇", "clips": [
    clip([f"{{ANA}} holds out a black envelope to {{NIKA}}. " + say("ANA", "ორმოცდაათი ათასი შენია."),
          f"{{NIKA}} does not take it. " + say("NIKA", "რა პირობით?", "coldly"),
          f"{{ANA}} leans in. " + say("ANA", "შემდეგ ექსპერიმენტს შენ წაიყვან."),
          f"Wide shot: everyone in the control room watches {{NIKA}} in silence; {{TEKLA}} looks away. No dialogue."],
         [V(0.4, 3.8, "ორმოცდაათი ათასი *შენია*."), V(4.4, 7.4, "რა *პირობით*?"),
          V(8.3, 10.9, "შემდეგ ექსპერიმენტს *შენ წაიყვან*."), N(11.3, "ნიკას *არჩევანი* უნდა გაეკეთებინა.")],
         light="bright white control room light", amb="electronic hum, silence"),
    clip([f"{{NIKA}} slowly takes the envelope, his face unreadable. No dialogue.",
          f"Dawn: {{NIKA}} walks out of the cabin into the foggy pine forest; a black minivan waits. No dialogue.",
          "Inside a new empty cabin room: six fresh name tags lie on a table; one hand places the last one down. No dialogue.",
          f"Close-up: {{NIKA}} turns and looks straight into the camera. " + say("NIKA", "ახლა შენი ჯერია.", "quietly, with a cold smile")],
         [N(0.3, "ნიკამ *კონვერტი აიღო*."), N(5.2, "ექსპერიმენტი *არ დასრულებულა*."),
          V(11.3, 14.4, "ახლა *შენი ჯერია*.")],
         light="warm dawn light, then cold interior", amb="birds, wind, car engine idling")]})


data = json.loads(P.read_text())
data["episodes"] = [e for e in data["episodes"] if e["n"] == 1] + EP
for e in data["episodes"]:
    e.setdefault("hashtags", ["#ექსპერიმენტი", "#სერიალი", "#თრილერი", "#საქართველო", "#fyp"])
P.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")
print(f"{len(data['episodes'])} episodes written")
