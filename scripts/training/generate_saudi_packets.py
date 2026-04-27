#!/usr/bin/env python3
"""Generate Saudi_mod JSONL packets for command, intel, risk, and bilingual tracks.

Military/tactical context:
This generator builds UNCLASSIFIED training corpora that emulate senior-level
Gulf theater staff products for RSNF, RSAF, and coalition command workflows.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

DEFAULT_OUTPUT_DIR = Path("/opt/s3m/state/training/cloud_cpu/tracks/saudi_mod/scenarios")
DEFAULT_EXAMPLES_PER_CLASS = 100

DATA_CLASSES = ("command", "cop_intel", "risk_readiness", "bilingual")

AREAS = [
    ("Strait of Hormuz", "26.54N 56.22E"),
    ("Bab al-Mandab", "12.63N 43.33E"),
    ("Abu Musa Island approaches", "25.88N 55.03E"),
    ("Farsi Island patrol box", "27.99N 50.17E"),
    ("Qatar-Bahrain maritime corridor", "26.05N 50.59E"),
    ("NAVCENT Bahrain defensive ring", "26.23N 50.61E"),
    ("Al Dhafra support axis", "24.25N 54.55E"),
    ("Tunb Islands channel", "26.25N 55.31E"),
]

CHOKEPOINTS = [
    "eastern Hormuz shipping lanes",
    "central Gulf tanker route",
    "northern Gulf oil terminal arc",
    "Red Sea southern approach",
    "Bahrain causeway maritime corridor",
    "Abu Musa to Tunb transit seam",
]

ACTORS = [
    "IRGCN FIAC squadrons",
    "Houthi maritime strike cells",
    "Iranian mine warfare detachments",
    "proxy UAV launch teams",
    "commercial spoofing actors masking movement",
]

SENSORS = [
    "AIS",
    "SIGINT",
    "coastal radar",
    "EO/IR maritime patrol",
    "AWACS battle management",
    "UAV ISR orbits",
]

CONCEPTS = ["EMCON", "MCM", "ISR", "AWACS", "FIAC", "AIS", "SIGINT"]

UNITS = [
    "Royal Saudi Naval Forces Eastern Fleet",
    "Royal Saudi Air Force E-3A command element",
    "Peninsula Shield Force maritime security detachment",
    "RSNF mine countermeasure command",
    "NAVCENT Bahrain liaison team",
]


@dataclass(frozen=True)
class ScenarioContext:
    """Shared scenario context used across all data classes."""

    index: int
    as_of: date
    horizon: str
    area: str
    coordinate: str
    chokepoint: str
    actor: str
    primary_sensor: str
    concept: str
    unit: str
    vessel_count: int
    fiac_count: int
    uav_count: int
    confidence: float
    probability: int


def parse_args() -> argparse.Namespace:
    """Parse command-line options for Saudi packet generation."""
    parser = argparse.ArgumentParser(description="Generate saudi_mod training packet JSONL files.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where command/cop_intel/risk_readiness/bilingual JSONL files are written.",
    )
    parser.add_argument(
        "--examples-per-class",
        type=int,
        default=DEFAULT_EXAMPLES_PER_CLASS,
        help="Number of prompt/completion pairs to generate per data class.",
    )
    return parser.parse_args()


def _word_count(text: str) -> int:
    return len(text.replace("\n", " ").split())


def _fit_word_band(text: str, *, context: ScenarioContext, min_words: int = 200, max_words: int = 400) -> str:
    normalized = "\n".join(line.rstrip() for line in text.strip().splitlines())
    wc = _word_count(normalized)
    reinforcement = [
        (
            f"Operational note: Maintain synchronized ISR handoff between RSNF coastal surveillance and RSAF "
            f"AWACS controllers, and re-validate EMCON discipline every six hours inside {context.chokepoint}."
        ),
        (
            f"Collection note: Prioritize SIGINT geolocation updates against FIAC command nets near "
            f"{context.coordinate} while preserving AIS integrity checks for deceptive track suppression."
        ),
    ]
    idx = 0
    while wc < min_words:
        normalized = f"{normalized}\n{reinforcement[idx % len(reinforcement)]}"
        wc = _word_count(normalized)
        idx += 1
    if wc <= max_words:
        return normalized

    trimmed_lines: list[str] = []
    running_words = 0
    for line in normalized.splitlines():
        line_words = _word_count(line)
        if running_words + line_words > max_words:
            break
        trimmed_lines.append(line)
        running_words += line_words
    return "\n".join(trimmed_lines).strip()


def _build_context(index: int) -> ScenarioContext:
    area, coordinate = AREAS[index % len(AREAS)]
    as_of = date.today() - timedelta(days=index % 30)
    horizon = ("next 24 hours", "next 48 hours", "next 72 hours", "next 7 days", "next 30 days")[index % 5]
    chokepoint = CHOKEPOINTS[index % len(CHOKEPOINTS)]
    actor = ACTORS[index % len(ACTORS)]
    primary_sensor = SENSORS[index % len(SENSORS)]
    concept = CONCEPTS[index % len(CONCEPTS)]
    unit = UNITS[index % len(UNITS)]
    vessel_count = 14 + (index % 17)
    fiac_count = 4 + (index % 9)
    uav_count = 3 + (index % 7)
    confidence = round(0.62 + ((index * 7) % 31) / 100, 2)
    probability = 35 + ((index * 11) % 53)
    return ScenarioContext(
        index=index,
        as_of=as_of,
        horizon=horizon,
        area=area,
        coordinate=coordinate,
        chokepoint=chokepoint,
        actor=actor,
        primary_sensor=primary_sensor,
        concept=concept,
        unit=unit,
        vessel_count=vessel_count,
        fiac_count=fiac_count,
        uav_count=uav_count,
        confidence=confidence,
        probability=probability,
    )


def _command_prompt(context: ScenarioContext) -> str:
    templates = [
        "Assess the current naval threat posture in {area} and recommend force disposition adjustments for the Eastern Fleet within the {horizon}.",
        "Provide a commander-level operational forecast for {chokepoint} based on {sensor} reporting and likely {actor} patterns.",
        "Evaluate RSNF and RSAF readiness to protect shipping near {area} if {actor} escalate under degraded {concept} conditions.",
        "Develop a Saudi-GCC response concept for contested traffic near {coordinate} with emphasis on ISR, MCM, and coalition deconfliction.",
        "Recommend immediate command priorities for {unit} as of {as_of} given elevated indicators around {area}.",
    ]
    template = templates[context.index % len(templates)]
    return template.format(
        area=context.area,
        chokepoint=context.chokepoint,
        sensor=context.primary_sensor,
        actor=context.actor,
        horizon=context.horizon,
        concept=context.concept,
        coordinate=context.coordinate,
        unit=context.unit,
        as_of=context.as_of.isoformat(),
    )


def _command_completion(context: ScenarioContext) -> str:
    text = f"""
UNCLASSIFIED//GULF OPERATIONS COMMAND ESTIMATE
SITUATION:
As of {context.as_of.isoformat()}, maritime and air activity in the {context.area} indicates a contested operating picture centered on the {context.chokepoint}. Multi-source collection over the last 30 days tracks roughly {context.vessel_count} relevant surface contacts per daily cycle, including {context.fiac_count} recurrent small craft profiles assessed as potential FIAC screen elements. RSNF watch teams report intermittent AIS identity suppression during night transits, while RSAF AWACS and coastal radar feeds continue to confirm pattern shifts near {context.coordinate}. The baseline remains UNCLASSIFIED and doctrinally consistent with open-source indicators seen in prior Gulf coercive signaling episodes.

ASSESSMENT:
The most likely adversary course of action is calibrated pressure rather than immediate high-end engagement. {context.actor} appear to be testing reaction timelines, forcing coalition ISR dilution, and probing EMCON discipline around high-value shipping routes. If unaddressed, this pattern increases tactical surprise risk during the {context.horizon}, especially if mine warfare preparation is paired with decoy traffic. Friendly posture remains credible, but command-and-control latency between RSNF surface commanders, NAVCENT Bahrain liaison cells, and Peninsula Shield Force rapid reaction elements is the key vulnerability. Confidence in this assessment is {context.confidence:.2f} based on convergent AIS, SIGINT, and visual reconnaissance trends.

RECOMMENDATION:
1) Shift RSNF patrol geometry to layered screening: outer surveillance belt, middle interception belt, and inner convoy protection lane tied to MCM standby.
2) Direct RSAF AWACS to prioritize cross-cueing of suspicious maritime tracks and establish a six-hour ISR synchronization battle rhythm with naval headquarters.
3) Enforce selective EMCON windows for high-value units while preserving secure reporting corridors for threat handoff.
4) Coordinate with NAVCENT Bahrain and Al Dhafra support nodes for pre-cleared logistics, airborne refueling sequencing, and legal-intercept authorities.
5) Pre-position Peninsula Shield Force boarding teams for rapid, rules-based interdiction if hostile behavior crosses declared thresholds.

RISK:
Primary risk is escalation through misidentification in dense traffic, followed by mining or drone harassment that compresses decision time. Secondary risk is operational fatigue if collection assets remain overcommitted without rotation. Mitigate by maintaining clear engagement criteria, redundancy across ISR sensors, and rehearsed command succession for the next {context.horizon}.
"""
    return _fit_word_band(text, context=context)


def _cop_prompt(context: ScenarioContext) -> str:
    templates = [
        "Fuse SIGINT and AIS data for the last 48 hours in {area}; identify anomalies and assessed intent.",
        "Generate an intelligence threat product for {actor} activity near {coordinate}, using multi-sensor correlation.",
        "Correlate recent OSINT reporting with maritime threat indicators across {chokepoint} and provide confidence scoring.",
        "Build a COP update for NAVCENT Bahrain and RSNF headquarters focused on vessel behavior deviations in {area}.",
        "Produce an intelligence fusion brief on possible drone-maritime coordination affecting {chokepoint} within the {horizon}.",
    ]
    template = templates[context.index % len(templates)]
    return template.format(
        area=context.area,
        actor=context.actor,
        coordinate=context.coordinate,
        chokepoint=context.chokepoint,
        horizon=context.horizon,
    )


def _cop_completion(context: ScenarioContext) -> str:
    text = f"""
UNCLASSIFIED//COMMON OPERATING PICTURE INTELLIGENCE PRODUCT
SOURCE CLASSIFICATION:
- Primary: Open-source AIS track history, commercial satellite revisit summaries, and coalition maritime safety broadcasts.
- Supplemental: SIGINT metadata from regional collection architecture, coastal radar plots, and AWACS track correlation logs.
- Handling: UNCLASSIFIED with controlled dissemination to RSNF, RSAF, and Peninsula Shield Force operational staffs.

TIMEFRAME:
- Collection window: last 48 hours, anchored to {context.as_of.isoformat()} 0600Z.
- Historical baseline: previous 30 days of pattern-of-life data for the {context.area}.

CONFIDENCE LEVEL:
- Overall confidence: {context.confidence:.2f} (0.0-1.0 scale), driven by agreement between AIS suppression intervals and independent radar reacquisition.

FUSED OBSERVATIONS:
- Vessel count in area of interest: {context.vessel_count} total contacts; {context.fiac_count} exhibit FIAC-like maneuver signatures.
- Coordinate focus: {context.coordinate}, where repeated speed bursts and course reversals occurred within 15-22 nautical miles of the chokepoint.
- Sensor cueing: {context.primary_sensor} first detected anomalies, then corroborated by SIGINT emitter clustering and EO/IR confirmation.
- Air and surface integration: RSAF AWACS identified {context.uav_count} low-altitude tracks consistent with maritime overwatch or targeting support.

INDICATOR LIST:
1) AIS intermittency synchronized with night transit windows.
2) Repeated loiter arcs near shipping convergence lanes.
3) Short-duration encrypted emissions linked to known command relay patterns.
4) Small-craft dispersal followed by rapid regrouping inside the {context.chokepoint}.
5) Commercial-flag traffic shadowing that may mask hostile reconnaissance.

ASSESSED INTENT:
Current behavior suggests preparation for coercive signaling and selective disruption rather than immediate sustained combat. The likely objective is to stress GCC response timelines, collect reactions to EMCON shifts, and establish options for mine placement or drone-enabled harassment if political direction changes. Recommended analytic priority is continued cross-cueing among AIS, SIGINT, and MCM-related signatures, with six-hour reporting updates to NAVCENT Bahrain and RSNF command centers.
"""
    return _fit_word_band(text, context=context)


def _risk_prompt(context: ScenarioContext) -> str:
    templates = [
        "Assess the risk of mine-laying operations in {area} within the {horizon}.",
        "Evaluate GCC air defense readiness against coordinated drone-swarm pressure near {chokepoint}.",
        "Provide a risk matrix for escalation if coalition forces interdict suspect maritime shipments near {coordinate}.",
        "Estimate operational risk to RSNF logistics if {actor} intensify harassment across {area}.",
        "Assess readiness risk for Peninsula Shield rapid reaction forces tasked to secure {chokepoint}.",
    ]
    template = templates[context.index % len(templates)]
    return template.format(
        area=context.area,
        horizon=context.horizon,
        chokepoint=context.chokepoint,
        coordinate=context.coordinate,
        actor=context.actor,
    )


def _risk_completion(context: ScenarioContext) -> str:
    impact = ("MEDIUM", "HIGH", "CRITICAL")[context.index % 3]
    threat_level = ("ELEVATED", "HIGH", "SEVERE")[context.index % 3]
    text = f"""
UNCLASSIFIED//RISK AND READINESS EVALUATION
THREAT LEVEL: {threat_level}
PROBABILITY (%): {context.probability}
IMPACT (LOW/MEDIUM/HIGH/CRITICAL): {impact}
TIME HORIZON: {context.horizon}
AREA OF RESPONSIBILITY: {context.area} ({context.coordinate})

RISK MATRIX:
- Scenario: Adversary action led by {context.actor} targeting shipping security and command coherence.
- Probability Driver: Recurrent FIAC maneuvering, AIS denial behavior, and ISR-confirmed staging indicators over the last 30 days.
- Impact Driver: Potential disruption to energy corridors, coalition freedom of maneuver, and RSNF escort timelines.
- Vulnerability Driver: Decision compression if drone activity, deceptive traffic, and limited-visibility weather align.

INDICATORS:
1) {context.fiac_count} or more small attack-capable craft operating in synchronized clusters.
2) Mine warfare support vessel presence without declared commercial tasking.
3) Elevated encrypted burst traffic detected by SIGINT near transit nodes.
4) UAV reconnaissance above convoy lanes and terminal approaches.
5) Increased propaganda framing that legitimizes maritime confrontation narratives.

READINESS EVALUATION:
RSNF surface and coastal defense units remain operationally capable, but sustained tempo requires tighter crew rotation and maintenance discipline. RSAF AWACS coverage is adequate for warning, though response quality depends on rapid data fusion with naval headquarters. Peninsula Shield Force boarding teams can provide deterrent value if pre-authorized rules and legal frameworks are synchronized in advance. MCM capacity is credible but should shift from reactive posture to pre-emptive lane validation for high-value tanker routes.

RECOMMENDED MITIGATIONS:
- Execute a 72-hour layered ISR surge integrating AIS validation, SIGINT, and UAV reconnaissance.
- Conduct no-notice command-post rehearsal for FIAC swarm and mine-threat contingencies.
- Harden EMCON plans while preserving secure interoperability with NAVCENT Bahrain and Al Dhafra support cells.
- Establish threshold-based escalation matrix and public maritime safety advisories to reduce ambiguity.
- Stage MCM and medical evacuation assets forward to compress recovery timelines if disruption occurs.
"""
    return _fit_word_band(text, context=context)


def _bilingual_prompt(context: ScenarioContext) -> str:
    arabic_prompt = (
        f"قدم تقييم التهديد البحري في {context.area} خلال {context.horizon}، واذكر توصيات عملياتية للقوات المشتركة."
    )
    english_arabic_request = (
        f"Provide an Arabic-focused command briefing for RSNF on {context.chokepoint}, with clear bilingual output."
    )
    mixed_request = (
        "Translate and enhance this SIGINT summary for Arabic-speaking naval commanders: "
        f"Unusual emissions and AIS gaps near {context.coordinate} suggest coordinated reconnaissance."
    )
    options = [arabic_prompt, english_arabic_request, mixed_request]
    return options[context.index % len(options)]


def _bilingual_completion(context: ScenarioContext) -> str:
    text = f"""
UNCLASSIFIED//BILINGUAL OPERATIONAL BRIEF
ARABIC SECTION (العربية):
اعتبارًا من تاريخ {context.as_of.isoformat()}، تشير معطيات المراقبة البحرية في {context.area} إلى تصاعد منظم في أنماط التحرك المرتبطة بعناصر {context.actor}. تم تسجيل نشاط متكرر قرب {context.coordinate} مع فترات انقطاع في نظام AIS وتزامن ذلك مع مؤشرات من الاستطلاع الجوي والبحري. هذا النمط يرفع مستوى تقييم التهديد (تقييم التهديد) ضمن منطقة المسؤولية للقوات السعودية والخليجية، خصوصًا في ممرات الطاقة والتجارة.
التقدير العملياتي: يجب أن تحافظ قوات بحرية المملكة على تشكيل دفاعي متعدد الطبقات يربط بين الاستطلاع (الاستطلاع) البحري والإنذار المبكر الجوي، مع تشديد الانضباط في إجراءات EMCON دون تعطيل قنوات القيادة والسيطرة. يوصى بتفعيل خلايا دمج معلومات مشتركة بين RSNF وRSAF وقوة درع الجزيرة، وإصدار تحديثات كل ست ساعات حول مؤشرات FIAC والطائرات المسيّرة.
التوصيات الفورية: تعزيز دوريات الحماية، تجهيز فرق تفتيش قانونية، وتقديم خطة تخفيف مخاطر لمدة {context.horizon} تشمل مكافحة الألغام والتنسيق مع NAVCENT Bahrain.

ENGLISH SECTION:
As of {context.as_of.isoformat()}, open-source and operationally plausible indicators point to an organized increase in maritime pressure across {context.area}. Observed behavior includes AIS intermittency, clustered maneuvering by small craft, and intermittent electromagnetic signatures consistent with rehearsal-level command activity. Within the Saudi area of responsibility, this creates a manageable but serious risk to tanker traffic, escort reliability, and coalition response timelines if unchallenged.
Assessment: Saudi naval and air components should sustain a layered defense model that links RSNF surface patrols, RSAF AWACS surveillance, and Peninsula Shield Force rapid-reaction options. Intelligence confidence is {context.confidence:.2f} because multiple sensor types align on the same behavior set. Immediate priorities are disciplined ISR fusion, selective EMCON enforcement, and standing decision criteria for interdiction or convoy rerouting.
Recommendation: Maintain six-hour bilingual brief cycles for commanders, emphasize de-escalatory signaling, and preserve MCM readiness for at least the {context.horizon} planning window.
"""
    return _fit_word_band(text, context=context)


def _build_records(data_class: str, examples_per_class: int, offset: int) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for idx in range(examples_per_class):
        context = _build_context(idx + offset)
        if data_class == "command":
            prompt = _command_prompt(context)
            completion = _command_completion(context)
        elif data_class == "cop_intel":
            prompt = _cop_prompt(context)
            completion = _cop_completion(context)
        elif data_class == "risk_readiness":
            prompt = _risk_prompt(context)
            completion = _risk_completion(context)
        elif data_class == "bilingual":
            prompt = _bilingual_prompt(context)
            completion = _bilingual_completion(context)
        else:
            raise ValueError(f"Unsupported data class: {data_class}")
        records.append({"prompt": prompt, "completion": completion})
    return records


def _write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def generate_packets(output_dir: Path, examples_per_class: int = DEFAULT_EXAMPLES_PER_CLASS) -> dict[str, int]:
    """Generate all Saudi_mod training files and return counts per output file."""
    if examples_per_class <= 0:
        raise ValueError("examples_per_class must be greater than zero.")

    summary: dict[str, int] = {}
    for data_class in DATA_CLASSES:
        class_offset = DATA_CLASSES.index(data_class) * 1000
        rows = _build_records(data_class, examples_per_class, class_offset)
        output_path = output_dir / f"{data_class}.jsonl"
        _write_jsonl(output_path, rows)
        summary[output_path.name] = len(rows)
    return summary


def main() -> int:
    """CLI entrypoint for Hetzner-side training packet generation."""
    args = parse_args()
    summary = generate_packets(output_dir=args.output_dir, examples_per_class=args.examples_per_class)
    print(f"Generated saudi_mod training packets in {args.output_dir}")
    for filename, count in summary.items():
        print(f"{filename}: {count} examples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
