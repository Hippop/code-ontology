"""Fixed independent verifier for platform self-development; no uploaded tests."""
import contextlib
import io
import json
import runpy
import sys
import unittest
from pathlib import Path


def main():
    root, output = map(Path,sys.argv[1:])
    sys.path[:0]=[str(root/"src"),str(root/"tests")]
    from rdflib import Graph, RDF, Namespace, RDFS
    dev=Namespace("https://example.org/code-ontology/development#")
    cases=[]
    # Kept independent of the generator's catalog: removing a domain from the
    # model or generated artifact must fail this acceptance rather than shrink it.
    ids={"metamodel","baseline","requirement","alignment","plan","generation","verification","audit","contract"}
    try:
        contract=runpy.run_path(str(output/"generated/platform_contract.py"))
        rows=contract["REQUIREMENTS"]
        graph=Graph().parse(output/"model.ttl",format="turtle")
        expected={str(s):{"iri":str(s),"label":str(graph.value(s,RDFS.label)),"scope":str(graph.value(s,dev.scope)),"statement":str(graph.value(s,dev.statement))} for s in graph.subjects(RDF.type,dev.Requirement)}
        assert len(rows)==9 and {row["iri"].rsplit(":req_",1)[-1] for row in rows}==ids
        assert {row["iri"]:row for row in rows}==expected
        assert all(contract["requirement"](iri)==row for iri,row in expected.items())
        assert contract["requirement"]("urn:unknown") is None
        ts=(output/"generated/platform-contract.ts").read_text(encoding="utf-8")
        payload=ts.split("export const requirements = ",1)[1].split(" as const;",1)[0]
        assert json.loads(payload)==rows
        cases.append({"id":"contract","passed":True,"tests":5,"skipped":0})
    except Exception as error:
        cases.append({"id":"contract","passed":False,"tests":5,"skipped":0,"error":str(error)})
    suites=(
        ("metamodel","test_metamodel_registry"), ("baseline","test_code_intelligence"),
        ("requirement","test_engineering_semantics"), ("alignment","test_requirement_reconciliation"),
        ("plan","test_execution_workflow"), ("generation","test_development_codegen"),
        ("verification","test_precommit_verification"), ("audit","test_platform"),
    )
    for key,module in suites:
        log=io.StringIO()
        with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
            suite=unittest.defaultTestLoader.loadTestsFromName(module)
            result=unittest.TextTestRunner(stream=log,verbosity=1).run(suite)
        cases.append({"id":key,"passed":result.wasSuccessful() and result.testsRun>0 and not result.skipped,
                      "tests":result.testsRun,"skipped":len(result.skipped),"log":log.getvalue()[-8000:]})
    passed=all(c["passed"] for c in cases)
    print(json.dumps({"passed":passed,"cases":cases},ensure_ascii=False))
    return 0 if passed else 1


if __name__=="__main__":
    raise SystemExit(main())
