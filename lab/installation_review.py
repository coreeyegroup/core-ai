"""Repository lifecycle evidence, without executing unreviewed upstream scripts."""
import json
import subprocess
from pathlib import Path
import manager
import native_host

# The file inventory is evidence of candidate entry points, not package qualification.
REVIEW={
 "addyosmani/agent-skills":("skills-and-hooks","Review native hooks and supporting Node validators.",["scripts/validate-skills.js","hooks/session-start.sh"]),
 "agiprolabs/claude-trading-skills":("offline-analytics","Extend reviewed analytics and provider-dependent recipes.",["skills/position-sizing/scripts/size_calculator.py"]),
 "anthropics/financial-services":("financial-plugins","Review DCF validator and financial provider permissions.",["scripts/validate.py","plugins/vertical-plugins/financial-analysis/skills/dcf-model/scripts/validate_dcf.py"]),
 "anthropics/skills":("document-tools","Qualify remaining document and skill programs independently.",["skills/pdf/scripts/check_fillable_fields.py"]),
 "ayghri/i-have-adhd":("native-extension","Review host-specific extension and context hooks.",["INSTALL.md","package.json","extensions/i-have-adhd.ts"]),
 "blader/humanizer":("instruction-and-validator","Review package validation and compatible host registration.",["package.json","scripts/validate-package.py"]),
 "cathrynlavery/diagram-design":("diagram-tools","Qualify complete diagram generation and rendering.",["scripts/axonometry.py"]),
 "composiohq/awesome-claude-skills":("mixed-ecosystem","Separate local executable packages, remote app permissions and instructions.",["mcp-builder/scripts/evaluation.py","slack-gif-creator/core/gif_builder.py"]),
 "dietrichgebert/ponytail":("native-extension","Review native hooks in a disposable host before enabling.",["INSTALL.md","package.json",".opencode/plugins/ponytail.mjs"]),
 "egonex-ai/understand-anything":("native-analysis-suite","Build pinned TypeScript core, graph engine, dashboard and MCP components.",["understand-anything-plugin/skills/understand/merge-batch-graphs.py"]),
 "gauss314/skills":("provider-dependent","Separate data retrieval from order endpoints; require individual provider approval.",["skills/fred-macro/scripts/fetch_series.py","skills/alpaca-data/scripts/download_stock_bars.py"]),
 "juliusbrussee/caveman":("native-suite","Review installer, host integrations and MCP packages in an isolated profile.",["INSTALL.md","package.json","mcp/package.json","agents/compile.mjs"]),
 "marian2js/trading-skills":("offline-analytics","Review additional workflows and input validation.",["skills/_lib/calculations.py"]),
 "mattpocock/skills":("skills-and-hooks","Review host workflows and supporting guardrails.",["package.json","scripts/check-frontmatter.mjs"]),
 "ml4t/skills":("instruction-and-libraries","Separate skill catalog from external ML4T library installation.",["scripts/generate_chapter_map.py"]),
 "multica-ai/andrej-karpathy-skills":("instruction-only","Register instructions in a compatible host; no standalone executable identified.",["README.md"]),
 "mvanhorn/last30days-skill":("research-providers","Offline pipeline qualified; live providers require credentials and network policy.",["pyproject.toml","skills/last30days/scripts/last30days.py"]),
 "nextlevelbuilder/ui-ux-pro-max-skill":("design-tools","Review remaining CLI and integration dependencies.",[".claude/skills/ui-ux-pro-max/scripts/search.py"]),
 "obra/superpowers":("native-extension","Run native registration probe, then model-driven qualification.",[".opencode/INSTALL.md",".opencode/plugins/superpowers.js"]),
 "openai/skills":("mixed-tools","Qualify remaining executable skills according to their manifests.",["skills/.curated/jupyter-notebook/scripts/new_notebook.py"]),
 "reddygopalkrishna/trading-skills":("offline-analytics","Qualify the complete TradeKit package separately.",["core/tradekit/indicators.py","core/tradekit/options.py"]),
 "staskh/trading_skills":("native-python-package","Review full Python 3.13+ package and MCP dependencies.",["pyproject.toml","src/trading_skills/black_scholes.py"]),
 "vercel-labs/agent-skills":("node-tools","Review build, optimization and provider-specific scripts.",["package.json","scripts/build-discovery-index.mjs"]),
 "wshobson/agents":("native-plugins","Review generated adapters, native plugins and evaluation runtime.",["tools/install_opencode.py","plugins/plugin-eval/pyproject.toml"]),
}

def classify(repo,inventory):
    family,action,candidates=REVIEW[repo]
    paths={f["path"] for f in inventory.get("files",[])}
    return {"family":family,"next_action":action,
        "entrypoints":[{"path":p,"present":p in paths} for p in candidates],
        "installation_state":"instruction-registration-review" if family=="instruction-only" else "upstream-capability-review-required",
        "candidate_counts":{kind:inventory.get("counts",{}).get(kind,0) for kind in ("program","hook","manifest","agent-candidate")}}

def native_evidence(root):
    evidence={"host":"OpenCode","state":"image-unavailable","model_execution":"not-qualified","plugin":"Superpowers"}
    try:
        image,version=native_host.inspect_image(native_host.IMAGE_TAG)
        evidence.update(state="image-installed",image=image,version=version)
        folder=manager.safe_path(root,"reports","native")
        if not folder.is_dir():return evidence
        # Only report metadata from exact current-image records, not raw CLI payloads.
        paths=sorted((p for p in folder.glob("*.json") if p.is_file() and not p.is_symlink()),key=lambda p:p.stat().st_mtime,reverse=True)[:30]
        for path in paths:
            if path.stat().st_size>256*1024:continue
            record=json.loads(path.read_text())
            plan=record.get("plan",{})
            if plan.get("image")!=image or plan.get("commit")!=native_host.COMMIT or record.get("approval")!=native_host.digest(plan):continue
            checks=[{"arguments":r.get("arguments"),"state":r.get("state")} for r in record.get("results",[]) if isinstance(r,dict)]
            evidence.update(state="registration-probe-recorded",checks=checks,report_id=path.stem)
            expected=native_host.plan(root,native_host.IMAGE_TAG)
            if plan!=expected:
                evidence["state"]="previous-probe-requires-current-review"
                continue
            if [r["state"] for r in checks]==["version-matched","registration-review-required","skills-visible"]:
                evidence["state"]="skills-visible-review-required"
            break
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):
        pass
    return evidence

def main():
    import argparse
    import gateway
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.home()/"core-ai-lab")
    args=parser.parse_args()
    data=gateway.build_catalog(args.root)
    print(json.dumps({"repositories":data["repositories"],"native":data["native"]},indent=2))

if __name__=="__main__":main()
