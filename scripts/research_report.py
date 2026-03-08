"""
Scheduled research report: Trading Bots, OpenClaw, OpenClaw+Trading
Uses Claude API with web search to find recent Reddit posts and news,
then generates a structured German report.
"""

import anthropic
import datetime


def main():
    client = anthropic.Anthropic()
    today = datetime.date.today().strftime("%d.%m.%Y")

    prompt = f"""Heute ist der {today}. Durchsuche das Web nach aktuellen Posts und News der letzten 48 Stunden zu folgenden Themen:

1. Suche auf Reddit (r/algotrading, r/ClaudeAI, r/ChatGPTCoding, r/openclaw) und im Web nach:
   - Trading Bots und algorithmischer Handel mit AI/LLMs
   - OpenClaw — Use Cases, Projekte und Erfahrungen
   - OpenClaw speziell für Trading oder Finance-Automatisierung

2. Finde die interessantesten und meistdiskutierten Beiträge/Diskussionen.

3. Erstelle einen strukturierten Report auf Deutsch mit diesen Abschnitten:

# Research Report — {today}

## 🤖 Trading & Finance Bots
Top Highlights und Diskussionen der letzten 48h

## 🦀 OpenClaw Use Cases
Interessante Projekte, die Leute bauen

## 🦀📈 OpenClaw + Trading
Spezifische Finance/Trading-Anwendungen

## 💡 Key Takeaways
3-5 Bullet Points, die man wissen sollte

---
Halte den Report kompakt (max 1 Seite). Fokus auf Signal, nicht Noise.
Gib bei jedem Punkt die Quelle/den Link an, wenn verfügbar."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        tools=[{"type": "web_search_20250305"}],
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract text from response
    report = ""
    for block in response.content:
        if block.type == "text":
            report += block.text

    # If the model did tool use and needs continuation, handle it
    while response.stop_reason == "tool_use":
        # Collect tool results
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                # For web_search, the API handles results automatically
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Search completed.",
                    }
                )

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            tools=[{"type": "web_search_20250305"}],
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response.content},
                {"role": "user", "content": tool_results},
            ],
        )

        for block in response.content:
            if block.type == "text":
                report += block.text

    # Write report to file
    with open("report.md", "w", encoding="utf-8") as f:
        f.write(report)

    print("Report generated successfully.")
    print(f"Length: {len(report)} characters")


if __name__ == "__main__":
    main()
