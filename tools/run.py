"""Run reference tests, cocotb simulations, waveform selections, or synthesis."""

import argparse
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "sim")]


def checked(command, **kwargs):
    print("+ " + " ".join(str(arg) for arg in command), flush=True)
    subprocess.run(command, check=True, cwd=ROOT, **kwargs)


def simulate(name, seed):
    from cocotb_tools.runner import get_runner

    build = ROOT / "build" / name
    build.mkdir(parents=True, exist_ok=True)
    runner = get_runner("icarus")
    runner.build(sources=[ROOT / "rtl/framelatch.sv", ROOT / "sim/framelatch_tb.sv"],
                 hdl_toplevel="framelatch_tb", build_dir=build,
                 build_args=["-Wall"], always=True)
    xml_path = runner.test(test_module="test_receiver", hdl_toplevel="framelatch_tb",
                          test_filter=None if name == "regression" else f"\\.{name}$", seed=seed,
                          test_dir=build, results_xml=str(build / "results.xml"),
                          waves=True, plusargs=["+dumpfile=trace.fst"],
                          extra_env={"FRAMELATCH_RESULTS": str(build),
                                     "FRAMELATCH_SEED": str(seed)})
    # Do not rely solely on the simulator exit code: cocotb may write failures
    # to its JUnit XML while the simulator itself exits successfully.
    cases = ET.parse(xml_path).findall(".//testcase")
    selected = cases if name == "regression" else [c for c in cases if c.get("name") == name]
    failures = [c.get("name") for c in selected if c.find("failure") is not None
                or c.find("error") is not None or c.find("skipped") is not None]
    if not selected or failures:
        raise RuntimeError(f"simulation did not pass: {failures or 'no test results'}")
    print(f"{name}: {len(selected)} tests passed (seed {seed})")
    return build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["unit", "test", "synth", "all"])
    parser.add_argument("--seed", type=int, default=1931)
    args = parser.parse_args()
    if args.command in ("unit", "test", "all"):
        checked([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    if args.command in ("test", "all"):
        simulate("regression", args.seed)
    if args.command in ("synth", "all"):
        build = ROOT / "build"
        build.mkdir(exist_ok=True)
        checked(["iverilog", "-g2012", "-Wall", "-s", "framelatch", "-o",
                 "build/compile.vvp", "rtl/framelatch.sv"])
        script = ("read_verilog -sv rtl/framelatch.sv; hierarchy -check -top framelatch; "
                  "synth -top framelatch; check -assert; stat; "
                  "write_json build/framelatch-netlist.json")
        checked(["yosys", "-Q", "-T", "-q", "-l", "build/synthesis.log", "-p", script])
        print("Icarus compile and Yosys synthesis/check passed; see build/synthesis.log")


if __name__ == "__main__":
    main()
