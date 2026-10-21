"""Where the feed looks for content: Product Faculty first, then its instructors."""

SITE = "https://productfaculty.com"
SITEMAP_URL = f"{SITE}/sitemap.xml"

# Only individual content pages are ingested, never index pages.
CONTENT_PREFIXES = {
    "/blog/": "Product Faculty blog",
    "/podcast/": "Product Faculty podcast",
    "/playbooks/": "Product Faculty playbook",
    "/frameworks/": "Product Faculty framework",
}

TOPICS = [
    "AI Product Strategy",
    "AI Evals",
    "Agents & Agentic Engineering",
    "AI Prototyping & Prompting",
    "AI-Native PM Workflow",
    "Product Leadership",
    "Career & Interviews",
    "User Psychology & Research",
    "Other",
]

# Product Faculty founder and instructors (from productfaculty.com).
PEOPLE = [
    {"name": "Moe Ali", "role": "Founder & CEO, Product Faculty"},
    {"name": "Rohan Varma", "role": "Product Lead, Codex at OpenAI"},
    {"name": "Shubham Saboo", "role": "Senior AI Product Manager, Google"},
    {"name": "Henry Shi", "role": "Member of Technical Staff, Anthropic"},
    {"name": "Pawel Huryn", "role": "Creator of The Product Compass"},
    {"name": "Jennifer Liu", "role": "Former Senior Director of AI Products, Google"},
    {"name": "Amit Fulay", "role": "VP of Product, Uber"},
    {"name": "Satyajeet Salgar", "role": "Director of Product, Google AI"},
    {"name": "Reah Miyara", "role": "Senior Director, Google Models"},
    {"name": "Joff Redfern", "role": "Former CPO at Atlassian; Menlo Ventures"},
]
