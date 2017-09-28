#!/usr/bin/env python

import sys, os.path
from collections import defaultdict
from math import ceil, pi, log
import ROOT
ROOT.PyConfig.IgnoreCommandLineOptions = True
ROOT.gROOT.SetBatch(True)

from PhysicsTools.NanoAOD.nanoDQM_cfi import nanoDQM, NoPlot, Plot1D, Count1D, shortDump

infile = sys.argv[1]
if not os.path.isfile(infile): raise RuntimeError

class Branch:
    def __init__(self, branch):
        self.name = branch.GetName()
        self.title = branch.GetTitle()
        self.counter = None
        self.good = True
        if branch.GetNleaves() != 1:
            sys.stderr.write("Cannot parse branch '%s' in tree %s (%d leaves)\n", tree.GetName(), branch.GetName(), branch.GetNleaves())
            self.good = False
            return
        self.leaf = branch.FindLeaf(branch.GetName())
        if not self.leaf:
            sys.stderr.write("Cannot parse branch '%s' in tree %s (no leaf)\n", tree.GetName(), branch.GetName())
            self.good = False
            return
        self.kind = self.leaf.GetTypeName()
        if self.leaf.GetLen() == 0 and self.leaf.GetLeafCount() != None:
            self.counter = self.leaf.GetLeafCount().GetName()

class BranchGroup:
    def __init__(self, name):
        self.name = name
        self.subs = []
    def append(self, sub):
        self.subs.append(sub)

tfile = ROOT.TFile.Open(infile)
tree = tfile.Get("Events")
allbranches = [ Branch(b) for b in tree.GetListOfBranches() ]
allbranches = [ b for b in allbranches if b.good ]
branchmap = dict((b.name,b) for b in allbranches )
branchgroups = defaultdict(dict)
iscounter = {}
for b in allbranches:
    if b.counter: iscounter[b.counter] = True
for b in allbranches:
    if b.name in iscounter: continue
    if "_" in b.name:
        head, tail = b.name.split("_",1)
        if head == "HLT": continue # no monitoring for these
    else:
        head, tail = b.name, ''
    branchgroups[head][tail] = b
    if b.counter and ('@size' not in branchgroups[head]):
        branchgroups[head]['@size'] = branchmap[b.counter]

pyout = open("newDQM.py", "w")
pyout.write("""# automatically generated by prepareDQM.py
import FWCore.ParameterSet.Config as cms
from PhysicsTools.NanoAOD.nanoDQM_tools_cff import *

nanoDQM = cms.EDAnalyzer("NanoAODDQM",
    vplots = cms.PSet(
""");

c1 = ROOT.TCanvas("c1","c1")
def smartRound(x):
    if abs(x) < 1e-7: return 0
    if x < 0: return -smartRound(-x)
    shift = pow(10,ceil(log(x,10))-1)
    xu = x/shift;
    if (xu > 30): xu = 5*ceil(xu/5)
    else: xu = ceil(xu)
    return xu*shift;
def autoPlot1D(name, col, branch):
    if branch.kind == "Bool_t":  
        return Plot1D(name, col, 2, -0.5, 1.5)
    xmin, xmax = tree.GetMinimum(branch.name), tree.GetMaximum(branch.name)
    if col == "@size":
        return Count1D(name, int(xmax+1 if xmax < 40 else 40), -0.5, xmax+0.5)
    if branch.kind == "Int_t" and "Idx" in name:
        return NoPlot(name)
    if branch.kind != "Float_t":
        xmin, xmax = map(int, (xmin,xmax))
        if xmax-xmin < 20:
            return Plot1D(name, col, xmax-xmin+1, xmin-0.5, xmax+0.5)
    elif name == "phi":
        return Plot1D(name, col, 20, -pi, pi)
    if xmin < 0 and xmax > 0: 
        xmin, xmax = min(xmin, -xmax), max(xmax, -xmin) # symmetrize
    elif xmax > 0 and xmin/xmax < 0.03: 
        xmin = 0
    xmin, xmax = map(smartRound, (xmin,xmax))
    return Plot1D(name, col, 20, xmin, xmax)

for head in sorted(branchgroups.iterkeys()):
    pset = getattr(nanoDQM.vplots, head, None)
    if not pset:
        print "%s <skipped as it's not in vplots>" % head
        continue
    print "%s" % head
    vpset = pset.plots
    allplots = [ (x.name.value(),x) for x in vpset ]
    existing = set(x[0] for x in allplots)
    found  = set()
    title  = dict( (n,x.title.value()) for (n,x) in allplots if x.kind.value() != "none" and x.title.value() )
    for (t,branch) in sorted(branchgroups[head].iteritems()):
        t_noat = t.replace("@","_")
        found.add(t_noat)
        if t_noat not in title: title[t_noat] = branch.title
        if t_noat not in existing: allplots.append( (t_noat,autoPlot1D(t_noat,t,branch)) )
    # update titles
    for k,v in allplots: 
        if title[k] and v.kind.value() != "none": v.title = title[k]
    allplots.sort()
    pyout.write("        %s = cms.PSet(\n" % head)
    seldump = pset.sels.dumpPython().replace("\n","\n            ") if len(pset.sels.parameterNames_()) else "cms.PSet()"
    pyout.write("            sels = %s,\n" % seldump)
    pyout.write("            plots = cms.VPSet(\n")
    for k,v in allplots:
        pyout.write("              %s %s,\n" % (" " if k in found else "#", shortDump(v)));
    pyout.write("            )\n")
    pyout.write("        ),\n")
pyout.write("    )\n)\n");

