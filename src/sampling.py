#!/usr/bin/env python

#
# $File: sampling.py $
# $LastChangedDate: 2009-10-11 17:41:30 -0500 (Sun, 11 Oct 2009) $
# $Rev: 3033 $
#
# This file is part of simuPOP, a forward-time population genetics
# simulation environment. Please visit http://simupop.sourceforge.net
# for details.
#
# Copyright (C) 2004 - 2009 Bo Peng (bpeng@mdanderson.org)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#


"""
This module provides classes and functions that could be used to draw samples
from a simuPOP population. These functions accept a list of parameters such
as ``subPops`` ((virtual) subpopulations from which samples will be drawn) and
``times`` (number of samples to draw) and return a list of populations. Both
independent individuals and dependent individuals (pedigrees) are supported.

Independent individuals could be drawn from any population. Pedigree
information is not necessary and is usually ignored. Unique IDs are not needed
either although such IDs could help you identify samples in the parent
population.

Pedigrees could be drawn from multi-generational populations or age-structured
populations. All individuals are required to have a unique ID (usually tracked
by operator ``idTagger`` and are stored in information field ``ind_id``).
Parents of individuals are usually tracked by operator ``pedigreeTagger`` and
are stored in information fields ``father_id`` and ``mother_id``. If parental
information is tracked using operator ``parentsTagger`` and information fields
``father_idx`` and ``mother_idx``, a function ``sampling.IndexToID`` can be
used to convert index based pedigree to ID based pedigree. Note that
``parentsTagger`` can not be used to track pedigrees in age-structured
populations because they require parents of each individual resides in a
parental generation.

All sampling functions support virtual subpopulations through parameter
``subPops``, although sample size specification might vary. This feature
allows you to draw samples with specified properties. For example, you
could select only female individuals for cases of a female-only disease,
or select individuals within certain age-range. If you specify a list
of (virtual) subpopulations, you are usually allowed to draw certain
number of individuals from each subpopulation.
"""

__all__ = [
    #
    'IndexToID',
    'DrawPedigree',
    # Classes that can be derived to implement more complicated
    # sampling scheme
    'baseSampler',
    'randomSampler',
    'caseControlSampler',
    'pedigreeSampler',
    'affectedSibpairSampler',
    'nuclearFamilySampler',
    'threeGenFamilySampler',
    'combinedSampler',
    # Functions to draw samples
    'DrawRandomSample',
    'DrawRandomSamples',
    'DrawCaseControlSample',
    'DrawCaseControlSamples',
    'DrawAffectedSibpairSample',
    'DrawAffectedSibpairSamples',
    'DrawNuclearFamilySample',
    'DrawNuclearFamilySamples',
    'DrawThreeGenFamilySample',
    'DrawThreeGenFamilySamples',
    'DrawCombinedSample',
    'DrawCombinedSamples',
    #
]

import exceptions, random

from simuPOP import AllAvail, Stat, pedigree, OutbredSpouse, CommonOffspring, FemaleOnly, \
    Affected

def isSequence(obj):
    return hasattr(obj, '__iter__')

def isNumber(obj):
    return isinstance(obj, (int, long, float))

def IndexToID(pop, idField='ind_id', fatherField='father_id', motherField='mother_id',
              fatherIndex='father_idx', motherIndex='mother_idx', reset=False):
    '''This function adds information field idField (default to ``'ind_id'``)
    to population ``pop`` and assigns an unique ID to every individual in this
    population. It then adds information fields fatherField (default to
    ``'fatherField'``) and motherField (default to ``'motherField'``) and set
    their values with IDs according to the established index based
    parents-children relationship. Existing information fields will be used if
    idField, fatherField or motherField already exist. This function uses a
    system-wide ID generator for unique IDs, which does not have to start from
    zero. A parameter ``reset`` could be used to reset starting ID to zero
    (if ``reset=True``) or a specified number (``reset=number``).
    '''
    pop.addInfoFields([idField, fatherField, motherField], -1)
    # set each individual's unique ID to idField
    TagID(pop, reset=reset, infoFields=idField)
    # save each individual's parents' IDs to fatherField and motherField
    for gen in range(pop.ancestralGens()-1, -1, -1):
        pop.useAncestralGen(gen)
        for ind in pop.individuals():
            if ind.info(fatherIndex) != -1:
                father = pop.ancestor(ind.info(fatherIndex), gen+1)
                ind.setInfo(father.info(idField), fatherField)
            if ind.info(motherIndex) != -1:
                mother = pop.ancestor(ind.info(motherIndex), gen+1)
                ind.setInfo(mother.info(idField), motherField)


# Pedigree drawing
def DrawPedigree(pedigree, filename=None, *args, **kwargs):
    '''A wrapper function that calls R to draw pedigree by outputting the
    pedigree to a format that is recognizable by R 'kinship' library. Aliased
    arguments could be used to pass parameters to functions ``pedigree``,
    ``plot`` and ``par``. Please refer to module ``simuPOP.plotter`` for
    details about aliased arguments.
    '''
    try:
        import plotter
    except ImportError:
        return
    #
    args = plotter.derivedArgs(
        defaultFuncs = ['plot'],
        allFuncs = ['par', 'plot', 'pedigree', 'dev_print'],
        defaultParams = {'par_xpd': True},
        **kwargs
    )
    # device
    plotter.newDevice()
    #
    r.library('kinship')
    set_default_mode(NO_CONVERSION)
    totalNum = 0
    id = []
    dadid = []
    momid = []
    sex = []
    affected = []
    pedid = []
    for gen in range(pedigree.ancestralGens(), -1, -1):
        pedigree.useAncestralGen(gen)
        if gen == pedigree.ancestralGens():
            NumTopGenInds = pedigree.popSize()
        # count total number of individuals in the pedigree from all generations
        totalNum += pedigree.popSize()
        id = range(1, totalNum+1)
        # set id, dadid, momid, sex and affected vectors for function r.pedigree
        # and set vector pedid for function r.plot(r.pedigree, id, ...)
        for idx, ind in enumerate(pedigree.individuals()):
            if pedigree.ancestralGens() == 2 and gen == 0 and ind.info('father_idx') != -1:
                dad = ind.info('father_idx') + 1 + NumTopGenInds
                mom = ind.info('mother_idx') + 1 + NumTopGenInds
            else:
                dad = ind.info('father_idx') + 1
                mom = ind.info('mother_idx') + 1
            dadid.append(dad)
            momid.append(mom)
            sex.append(ind.sex())
            if ind.affected():
                affected.append(2)
            else:
                affected.append(1)
            pedid.append('%d-%d' % (gen, idx))
    # create an object of pedigree structure recognizable by R library
    ptemp = r.pedigree(id=id, dadid=dadid, momid=momid, sex=sex, affected=affected)
    # plot the pedigree structure
    plotter.r.par(**args.getArgs('par', None))
    plotter.r.plot(ptemp, id=pedid)
    plotter.saveFigure(**args.getArgs('dev_print', None, file=filename))
    plotter.r.dev_off()


# Sampling classes and functions

class baseSampler:
    '''
    A sampler extracts individuals from a simuPOP population and return them
    as separate populations. This base class defines the common interface of
    all sampling classes, including how samples prepared and returned.
    '''
    def __init__(self, subPops = AllAvail):
        '''Create a sampler with parameter ``subPops``, which will be used
        to prepare population for sampling. ``subPops`` should be a list of
        (virtual) subpopulations from which samples are drawn. The default
        value is AllAvail, which means all available subpopulations of a
        population.
        '''
        self.subPops = subPops
        self.pop = None

    def prepareSample(self, pop, rearrange):
        '''Prepare passed population object for sampling according to parameter
        ``subPops``. If samples are drawn from the whole population, a
        population will be trimmed if only selected (virtual) subpopulations
        are used. If samples are drawn separately from specified subpopulations,
        population ``pop`` will be rearranged (if ``rearrange==True``) so that
        each subpoulation corresponds to one element in parameter ``subPops``.
        '''
        if self.subPops == AllAvail:
            self.pop = pop
        else:
            self.pop = pop.extractSubPops(self.subPops, rearrange);
        return True

    def drawSample(self, pop):
        '''
        Draw and return a sample.
        '''
        raise SystemError('Please re-implement this drawSample function in the derived class.')

    def drawSamples(self, pop, times):
        '''
        Draw multiple samples and return a list of populations.
        '''
        if times < 0:
            raise ValueError("Negative number of samples are unacceptable")
        # 
        return [self.drawSample(pop) for x in range(times)]


class randomSampler(baseSampler):
    def __init__(self, size, subPops):
        baseSampler.__init__(self, subPops)
        self.size = size

    def drawSample(self, input_pop):
        '''Draw a random sample from passed population.
        '''
        if self.pop is None:
            # this will produce self.pop.
            self.prepareSample(input_pop, isSequence(self.size))
        #
        if not isSequence(self.size):
            size = self.size
            if size > self.pop.popSize():
                print 'Warning: sample size %d is greater than population size %d.' % (size, self.pop.popSize())
                size = pop.popSize()
            # randomly choose size individuals
            values = range(self.pop.popSize())
            random.shuffle(values)
            indexes = values[:size]
        else:
            indexes = []
            for sp in range(self.pop.numSubPop()):
                size = self.size[sp]
                if size > self.pop.subPopSize(sp):
                    print 'Warning: sample size (%d) at subpopulation %d is greater than subpopulation size %d ' \
                        % (size, sp, self.pop.subPopSize(sp))
                values = range(self.pop.subPopBegin(sp), self.pop.subPopEnd(sp))
                random.shuffle(values)
                indexes.extend(values[:size])
        return self.pop.extractIndividuals(indexes = indexes)


def DrawRandomSample(pop, size, subPops=AllAvail):
    '''Draw ``times`` random samples from a population. If a single ``size``
    is given, individuals are drawn randomly from the whole population or
    from specified (virtual) subpopulations (parameter ``subPops``). Otherwise,
    a list of numbers should be used to specify number of samples from each
    subpopulation, which can be all subpopulations if ``subPops=AllAvail``
    (default), or from each of the specified (virtual) subpopulations. This
    function returns a population with all extracted individuals.
    '''
    return randomSampler(size=size, subPops=subPops).drawSample(pop)


def DrawRandomSamples(pop, size, times=1, subPops=AllAvail):
    '''Draw ``times`` random samples from a population and return a list of
    populations. Please refer to function ``DrawRandomSample`` for more details
    about parameters ``size`` and ``subPops``.'''
    return randomSampler(size=size, subPops=subPops).drawSamples(pop, times=times)


class caseControlSampler(baseSampler):
    def __init__(self, cases, controls, subPops = AllAvail):
        baseSampler.__init__(self, subPops)
        self.cases = cases
        self.controls = controls
        if type(self.cases) != type(controls):
            raise exceptions.ValueError("Parameter cases and controls should have the same type.")
        if isSequence(self.cases) and isSequence(self.controls) and \
            len(self.cases) != len(self.controls):
            raise exceptions.ValueError("Cases and controls should have the same type")

    def prepareSample(self, input_pop):
        '''Find out indexes all affected and unaffected individuales.
        '''
        baseSampler.prepareSample(self, input_pop, isSequence(self.cases))
        if self.pop is None:
            # this will produce self.pop and self.cases and self.controls
            self.prepareSample(input_pop)
        #
        if not isSequence(self.cases):
            # find affected individuals
            self.affected = []
            self.unaffected = []
            for idx,ind in enumerate(self.pop.individuals()):
                if ind.affected():
                    self.affected.append(idx)
                else:
                    self.unaffected.append(idx)
            #
            if self.cases > len(self.affected):
                print 'Warning: number of cases %d is greater than number of self.affectedected individuals %d.' \
                    % (self.cases, len(self.affected))
            #
            if self.controls > len(self.unaffected):
                print 'Warning: number of controls %d is greater than number of self.affectedected individuals %d.' \
                    % (self.controls, len(self.unaffected))
        else:
            if len(self.cases) != self.pop.numSubPop():
                raise ValueError('If an list of cases is given, it should be specified for all subpopulations')
            self.affected = []
            self.unaffected = []
            for sp in range(self.pop.numSubPop()):
                # find self.affectedected individuals
                aff = []
                unaff = []
                for idx in range(self.pop.subPopBegin(sp), self.pop.subPopEnd(sp)):
                    if self.pop.individual(idx).affected():
                        aff.append(idx)
                    else:
                        unaff.append(idx)
                #
                if self.cases[sp] > len(aff):
                    print 'Warning: number of cases %d is greater than number of self.affectedected individuals %d in subpopulation %d.' \
                        % (self.cases[sp], len(aff), sp)
                #
                if self.controls[sp] > len(unaff):
                    print 'Warning: number of controls %d is greater than number of self.affectedected individuals %d in subpopulation %d.' \
                        % (self.controls[sp], len(unaff), sp)

    def drawSample(self, input_pop):
        '''Draw a case control sample
        '''
        if self.pop is None:
            # this will produce self.pop and self.affected and self.unaffected
            self.prepareSample(input_pop)
        #
        if not isSequence(self.cases):
            random.shuffle(self.affected)
            random.shuffle(self.unaffected)
            indexes = self.affected[:self.cases] + self.unaffected[:self.controls]
        else:
            indexes = []
            for sp in range(self.pop.numSubPop()):
                random.shuffle(self.affected[sp])
                random.shuffle(self.unaffected[sp])
                indexes.extend(self.affected[:self.cases[sp]])
                indexes.extend(self.unaffected[:self.controls[sp]])
        return self.pop.extractIndividuals(indexes = indexes)


def DrawCaseControlSample(pop, cases, controls, subPops=AllAvail):
    '''Draw a case-control samples from a population with ``cases``
    affected and ``controls`` unaffected individuals. If single ``cases`` and
    ``controls`` are given, individuals are drawn randomly from the whole
    population or from specified (virtual) subpopulations (parameter
    ``subPops``). Otherwise, a list of numbers should be used to specify
    number of cases and controls from each subpopulation, which can be all
    subpopulations if ``subPops=AllAvail`` (default), or from each of the
    specified (virtual) subpopulations. This function returns a population with
    all extracted individuals.
    '''
    return caseControlSampler(cases, controls, subPops).drawSample(pop) 


def DrawCaseControlSamples(pop, cases, controls, times=1, subPops=AllAvail):
    '''Draw ``times`` case-control samples from a population with ``cases``
    affected and ``controls`` unaffected individuals and return a list of
    populations. Please refer to function ``DrawCaseControlSample`` for a
    detailed descriptions of parameters.
    '''
    return caseControlSampler(cases, controls, subPops).drawSamples(pop, times) 


class pedigreeSampler(baseSampler):
    def __init__(self, families, subPops=AllAvail, idField='ind_id', fatherField='father_idx', motherField='mother_idx'):
        '''
        families
            number of families. This can be a number or a list of numbers. In
            the latter case, specified families are drawn from each
            subpopulation.

        subPops
            A list of (virtual) subpopulations from which samples are drawn.
            The default value is AllAvail, which means all available
            subpopulations of a population.
        '''
        baseSampler.__init__(self, subPops)
        self.families = families
        self.idField = idField
        self.fatherField = fatherField
        self.motherField = motherField
        self.pedigree = None

    def prepareSample(self, pop, loci=[], infoFields=[], ancGen=-1):
        '''
        Prepare self.pedigree, some pedigree sampler might need additional loci and
        information fields for this sampler.
        '''
        # create self.pop
        baseSampler.prepareSample(self, pop, isSequence(self.families))
        # get self.pedigree
        self.pedigree = pedigree(self.pop, loci, infoFields,
            ancGen, self.idField, self.fatherField, self.motherField)


class affectedSibpairSampler(pedigreeSampler):
    def __init__(self, families, subPops, idField='ind_id', fatherField='father_idx', motherField='mother_idx'):
        '''
        '''
        pedigreeSampler.__init__(self, families, subPops, idField, fatherField, motherField)

    def prepareSample(self, input_pop):
        'Find the father or all affected sibpair families'
        # this will give us self.pop and self.pedigree
        pedigreeSampler.prepareSample(self, input_pop, isSequence(self.families))
        if isSequence(self.families) and len(self.families) != self.pop.numSubPop():
            raise ValueError('If an list of family counts is given, it should be specified for all subpopulations')
        #
        # locate all affected siblings
        self.pedigree.addInfoFields(['spouse', 'off1', 'off2'])
        # only look for wife so families will not overlap
        self.pedigree.locateRelatives(OutbredSpouse, ['spouse'], FemaleOnly)
        # look for affected offspring
        self.pedigree.locateRelatives(CommonOffspring, ['spouse', 'off1', 'off2'], affectionStatus=Affected)
        # find qualified families
        if not isSequence(self.families):
            self.father_IDs = list(self.pedigree.individualsWithRelatives(['spouse', 'off1', 'off2']))
        else:
            self.father_IDs = []
            for sp in range(self.pedigree.numSubPop()):
                self.father_IDs.append(list(self.pedigree.individualsWithRelatives(['spouse', 'off1', 'off2'], subPops=sp)))

    def drawSample(self, input_pop):
        if self.pedigree is None:
            # this will give us self.pop, self.pedigree, and self.father_IDs
            self.prepareSample(input_pop)
        #
        if not isSequence(self.families):
            if self.families > len(self.father_IDs):
                print 'Warning: number of requested sibpairs %d is greater than what exists (%d).' \
                    % (self.families, len(self.father_IDs))
            #
            random.shuffle(self.father_IDs)
            selected_IDs = self.father_IDs[:self.families]
        else:
            selected_IDs = []
            for sp in range(self.pop.numSubPop()):
                if self.families[sp] > len(self.father_IDs[sp]):
                    print 'Warning: number of requested sibpairs %d is greater than what exists (%d) in subpopulation %d.' \
                        % (self.families[sp], len(self.father_IDs[sp]), sp)
                #
                random.shuffle(self.father_IDs[sp])
                selected_IDs.extend(self.father_IDs[sp][:self.families[sp]])
        # get father, spouse and their offspring
        IDs = []
        for id in selected_IDs:
            ind = self.pedigree.indByID(id)
            IDs.extend([id, ind.spouse, ind.off1, ind.off2])
        return self.pop.extractIndividuals(IDs = IDs, idField = self.idField)


def DrawAffectedSibpairSample(pop, families, subPops=AllAvail, 
    idField='ind_id', fatherField='father_id', motherField='mother_id'):
    '''Draw affected sibpair samples from a population. If a single
    ``families`` is given, affected sibpairs and their parents are drawn
    randomly from the whole population or from specified (virtual)
    subpopulations (parameter ``subPops``). Otherwise, a list of numbers should
    be used to specify number of families from each subpopulation, which can be
    all subpopulations if ``subPops=AllAvail`` (default), or from each of the
    specified (virtual) subpopulations. This function returns a population that
    contains extracted individuals.
    '''
    return affectedSibpairSampler(families, subPops, idField, fatherField,
        motherField).drawSample(pop)
 

def DrawAffectedSibpairSamples(pop, families, times=1, subPops=AllAvail, 
    idField='ind_id', fatherField='father_id', motherField='mother_id'):
    '''Draw ``times`` affected sibpair samplesa from population ``pop`` and
    return a list of populations. Please refer to function
    ``DrawAffectedSibpairSample`` for a description of other parameters.
    '''
    return affectedSibpairSample(families, subPops, idField, fatherField,
        motherField).drawSamples(pop, times)

class nuclearFamilySampler(pedigreeSampler):
    def __init__(self, families, numOffspring, affectedParents, affectedOffspring,
        subPops, idField='ind_id', fatherField='father_idx', motherField='mother_idx'):
        '''
        families
            number of families. This can be a number or a list of numbers. In the latter
            case, specified families are drawn from each subpopulation.

        numOffspring
            number of offspring. This can be a fixed number or a range [min, max].

        affectedParents
            number of affected parents. This can be a fixed number or a range [min, max].

        affectedOffspring
            number of affected offspring. This can be a fixed number of a range [min, max].

        subPops
            A list of (virtual) subpopulations from which samples are drawn.
            The default value is AllAvail, which means all available
            subpopulations of a population.
        '''
        if isNumber(numOffspring):
            if numOffspring < 1:
                raise ValueError('Number of offsprings must be equal to or larger than 1.')
            self.numOffspring = numOffspring, numOffspring
        elif isSequence(numOffspring):
            if len(numOffspring) != 2:
                raise ValueError('Two boundary numbers are needed for the allowed range of number of offsprings')
            if numOffspring[0] < 1 or numOffspring[0] > numOffspring[1]:
                raise ValueError('Minimum number of offsprings must not be smaller than 1 or larger than maximum number of offsprings.')
            self.numOffspring = numOffspring
        else:
            raise ValueError('Number of offsprings should be an integer number or a range of allowed values.')
        #
        if isNumber(affectedParents):
            if affectedParents not in [0, 1, 2]:
                raise ValueError('Number of affected individuals in parents can only take 0 or 1 or 2.')
            self.affectedParents = affectedParents, affectedParents
        elif isSequence(affectedParents):
            if len(affectedParents) != 2:
                raise ValueError('Two boundary numbers are needed for the range of number of affected parents.')
            if affectedParents[0] not in [0,1,2] or affectedParents[1] not in [0,1,2] or affectedParents[0] > affectedParents[1]:
                raise ValueError('Range of number of affected parents must be within (0, 2).')
            self.affectedParents = affectedParents
        else:
            raise ValueError('Number of affected parents should be an integer number (<= 2) or a range of allowed values.')
        #
        if isNumber(affectedOffspring):
            if affectedOffspring > self.numOffspring[1]:
                raise ValueError('Number of affected offsprings cannot be larger than number of offsprings.')
            self.affectedOffspring = affectedOffspring, affectedOffspring
        elif isSequence(affectedOffspring):
            if len(affectedOffspring) != 2:
                raise ValueError('Two boundary numbers are needed for the range of number of affected offsprings.')
            if affectedOffspring[0] > self.numOffspring[1]:
                raise ValueError('Minimum number of affected offsprings cannot be larger than number of offsprings.')
            self.affectedOffspring = affectedOffspring
        else:
            raise ValueError('Number of affected offsprings should be a proper integer nubmer or a range of allowed values.')
        #
        pedigreeSampler.__init__(self, families, subPops, idField, fatherField, motherField)

    def prepareSample(self, input_pop):
        # this will give us self.pop and self.pedigree
        pedigreeSampler.prepareSample(self, input_pop, isSequence(self.families))
        if isSequence(self.families) and len(self.families) != self.pop.numSubPop():
            raise ValueError('If an list of family counts is given, it should be specified for all subpopulations')
        #
        # locate all affected siblings
        minOffFields = ['off%d' % x for x in range(self.numOffspring[0])]
        offFields = ['off%d' % x for x in range(self.numOffspring[1])]
        self.pedigree.addInfoFields(['spouse'] + offFields)
        # only look for wife so families will not overlap
        self.pedigree.locateRelatives(OutbredSpouse, ['spouse'], FemaleOnly)
        # look for offspring
        self.pedigree.locateRelatives(CommonOffspring, ['spouse'] + offFields)
        # check number of affected individuals and filter them out.
        def qualify(id):
            father = self.pedigree.indByID(id)
            mother = self.pedigree.indByID(father.info('spouse'))
            parAff = father.affected() + mother.affected()
            if parAff < self.affectedParents[0] or parAff > self.affectedParents[1]:
                return False
            offID = [father.info('off%d' % x) for x in range(self.numOffspring[1])]
            offAff = sum([self.pedigree.indByID(id).affected() for id in offID if id >= 0])
            if offAff < self.affectedOffspring[0] or offAff > self.affectedOffspring[1]:
                return False
            return True
        # find all families with at least minOffFields...
        if not isSequence(self.families):
            self.father_IDs = filter(qualify, self.pedigree.individualsWithRelatives(['spouse'] + minOffFields))
        else:
            self.father_IDs = []
            for sp in range(self.pedigree.numSubPop()):
                self.father_IDs.append(filter(quality, self.pedigree.individualsWithRelatives(['spouse'] + minOffFields, subPops=sp)))

    def drawSample(self, input_pop):
        if self.pedigree is None:
            # this will give us self.pop, self.pedigree, and self.father_IDs
            self.prepareSample(input_pop)
        #
        if not isSequence(self.families):
            if self.families > len(self.father_IDs):
                print 'Warning: number of requested sibpairs %d is greater than what exists (%d).' \
                    % (self.families, len(self.father_IDs))
            #
            random.shuffle(self.father_IDs)
            selected_IDs = self.father_IDs[:self.families]
        else:
            selected_IDs = []
            for sp in range(self.pop.numSubPop()):
                if self.families[sp] > len(self.father_IDs[sp]):
                    print 'Warning: number of requested sibpairs %d is greater than what exists (%d) in subpopulation %d.' \
                        % (self.families[sp], len(self.father_IDs[sp]), sp)
                #
                random.shuffle(self.father_IDs[sp])
                selected_IDs.extend(self.father_IDs[sp][:self.families[sp]])
        # get father, spouse and their offspring
        IDs = []
        for id in selected_IDs:
            ind = self.pedigree.indByID(id)
            offIDs = [ind.info('off%d' % x) for x in range(self.numOffspring[1])]
            IDs.extend([id, ind.spouse] + [x for x in offIDs if x >= 0])
        return self.pop.extractIndividuals(IDs = IDs, idField = self.idField)


def DrawNuclearFamilySample(pop, families, numOffspring, affectedParents,
    affectedOffspring, subPops=AllAvail, idField='ind_id', fatherField='father_id',
    motherField='mother_id'):
    '''Draw nuclear families from a population. Number of offspring, number of
    affected parents and number of affected offspring should be specified using
    parameters ``numOffspring``, ``affectedParents`` and ``affectedOffspring``,
    which can all be a single number, or a range ``[a, b]`` (``b`` is incldued).
    If a single ``families`` is given, pedigrees are drawn randomly from the
    whole population or from specified (virtual) subpopulations (parameter
    ``subPops``). Otherwise, a list of numbers should be used to specify
    numbers of families from each subpopulation, which can be all
    subpopulations if ``subPops=AllAvail`` (default), or from each of the
    specified (virtual) subpopulations. This function returns a population that
    contains extracted individuals.
    '''
    return nuclearFamilySampler(families, numOffspring, affectedParents,
        affectedOffspring, subPops, idField, fatherField, motherField).drawSample(pop)
 

def DrawNuclearFamilySamples(pop, families, numOffspring, affectedParents,
    affectedOffspring, times=1, subPops=AllAvail, idField='ind_id',
    fatherField='father_id', motherField='mother_id'):
    '''Draw ``times`` affected sibpair samplesa from population ``pop`` and
    return a list of populations. Please refer to function
    ``DrawNuclearFamilySample`` for a description of other parameters.
    '''
    return nuclearFamilySample(families, numOffspring, affectedParents,
        affectedOffspring, subPops, idField, fatherField,
        motherField).drawSamples(pop, times)


class threeGenFamilySampler(pedigreeSampler):
    def __init__(self, families, numOffspring, pedSize, numAffected,
        subPops, idField='ind_id', fatherField='father_idx', motherField='mother_idx'):
        '''
        families
            number of families. This can be a number or a list of numbers. In the latter
            case, specified families are drawn from each subpopulation.

        numOffspring
            number of offspring. This can be a fixed number or a range [min, max].

        pedSize
            number of individuals in the pedigree. This can be a fixed number or
            a range [min, max].

        numAfffected
            number of affected individuals in the pedigree. This can be a fixed number
            or a range [min, max]

        subPops
            A list of (virtual) subpopulations from which samples are drawn.
            The default value is AllAvail, which means all available
            subpopulations of a population.
        '''
        if isNumber(numOffspring):
            if numOffspring < 1:
                raise ValueError('Number of offsprings must be equal to or larger than 1.')
            self.numOffspring = numOffspring, numOffspring
        elif isSequence(numOffspring):
            if len(numOffspring) != 2:
                raise ValueError('Two boundary numbers are needed for the allowed range of number of offsprings')
            if numOffspring[0] < 1 or numOffspring[0] > numOffspring[1]:
                raise ValueError('Minimum number of offsprings must not be smaller than 1 or larger than maximum number of offsprings.')
            self.numOffspring = numOffspring
        else:
            raise ValueError('Number of offsprings should be an integer number or a range of allowed values.')
        #
        if isNumber(pedSize):
            self.pedSize = pedSize, pedSize
        elif isSequence(pedSize):
            if len(pedSize) != 2:
                raise ValueError('Two boundary numbers are needed for the range of number of individuals in a pedigree.')
            self.pedSize = pedSize
        else:
            raise ValueError('Number of affected parents should be an integer number (<= 1) or a range of allowed values.')
        #
        if isNumber(numAffected):
            if numAffected > self.pedSize[1]:
                raise ValueError('Number of affected individuals cannot be larger than pedigree size.')
            self.numAffected = numAffected, numAffected
        elif isSequence(numAffected):
            if len(numAffected) != 2:
                raise ValueError('Two boundary numbers are needed for the range of number of affected individuals.')
            if numAffected[0] > self.pedSize[1]:
                raise ValueError('Minimum number of affected offsprings cannot be larger than number of individuals in a pedigree.')
            self.numAffected = numAffected
        else:
            raise ValueError('Number of affected offsprings should be a proper integer nubmer or a range of allowed values.')
        #
        pedigreeSampler.__init__(self, families, subPops, idField, fatherField, motherField)

    def prepareSample(self, input_pop):
        # this will give us self.pop and self.pedigree
        pedigreeSampler.prepareSample(self, input_pop, isSequence(self.families))
        if isSequence(self.families) and len(self.families) != self.pop.numSubPop():
            raise ValueError('If an list of family counts is given, it should be specified for all subpopulations')
        #
        # locate all affected siblings
        minOffFields = ['off%d' % x for x in range(self.numOffspring[0])]
        offFields = ['off%d' % x for x in range(self.numOffspring[1])]
        minGrandOffFields = ['goff%d' % x for x in range(self.numOffspring[0]**2)]
        grandOffFields = ['goff%d' % x for x in range(self.numOffspring[1]**2)]
        self.pedigree.addInfoFields(['spouse'] + offFields + grandOffFields)
        # only look for wife so families will not overlap
        self.pedigree.locateRelatives(OutbredSpouse, ['spouse'], FemaleOnly)
        # look for offspring
        self.pedigree.locateRelatives(CommonOffspring, ['spouse'] + offFields)
        # look for grand children
        self.pedigree.traceRelatives(fieldPath = [offFields, offFields], resultFields = grandOffFields)
        # check number of affected individuals and filter them out.
        def qualify(id):
            father = self.pedigree.indByID(id)
            mother = self.pedigree.indByID(father.spouse)
            offID = [father.info('off%d' % x) for x in range(self.numOffspring[1])]
            offID = [x for x in offID if x >= 0]
            offSpouseID = [self.pedigree.indByID(id).spouse for x in offID]
            grandOffID = [father.info('goff%d' % x) for x in range(self.numOffspring[1]**2)]
            grandOffID = [x for x in grandOffID if x >= 0]
            pedSize = 2 + len(offID) + len(offSpouseID) + grandOffID
            if pedSize < self.pedSize[0] or pedSize > self.pedSize[1]:
                return False
            # check number of affected individuals
            numAff = sum([self.pedigree.indByID(id).affected() for id in offID + offSpouseID + grandOffID]) + father.affected() + mother.affected()
            if numAff < self.numAffected[0] or numAff > self.numAffected[1]:
                return False
            return True
        # find all families with at least minOffFields...
        if not isSequence(self.families):
            self.father_IDs = filter(qualify, self.pedigree.individualsWithRelatives(['spouse'] + minOffFields + minGrandOffFields))
        else:
            self.father_IDs = []
            for sp in range(self.pedigree.numSubPop()):
                self.father_IDs.append(filter(quality, self.pedigree.individualsWithRelatives(['spouse'] + minOffFields + minGrandOffFields, subPops=sp)))

    def drawSample(self, input_pop):
        if self.pedigree is None:
            # this will give us self.pop, self.pedigree, and self.father_IDs
            self.prepareSample(input_pop)
        #
        if not isSequence(self.families):
            if self.families > len(self.father_IDs):
                print 'Warning: number of requested sibpairs %d is greater than what exists (%d).' \
                    % (self.families, len(self.father_IDs))
            #
            random.shuffle(self.father_IDs)
            selected_IDs = self.father_IDs[:self.families]
        else:
            selected_IDs = []
            for sp in range(self.pop.numSubPop()):
                if self.families[sp] > len(self.father_IDs[sp]):
                    print 'Warning: number of requested sibpairs %d is greater than what exists (%d) in subpopulation %d.' \
                        % (self.families[sp], len(self.father_IDs[sp]), sp)
                #
                random.shuffle(self.father_IDs[sp])
                selected_IDs.extend(self.father_IDs[sp][:self.families[sp]])
        # get father, spouse, offspring, spouse of offspring and grandchildren
        IDs = []
        for id in selected_IDs:
            father = self.pedigree.indByID(id)
            spouseID = father.spouse
            offID = [father.info('off%d' % x) for x in range(self.numOffspring[1])]
            offID = [x for x in offID if x >= 0]
            offSpouseID = [self.pedigree.indByID(id).spouse for x in offID]
            grandOffID = [father.info('goff%d' % x) for x in range(self.numOffspring[1]**2)]
            grandOffID = [x for x in grandOffID if x >= 0]
            IDs.extend([id, spouseID] + offID + offSpouseID + grandOffID)
        return self.pop.extractIndividuals(IDs = IDs, idField = self.idField)


def DrawThreeGenFamilySample(pop, families, numOffspring, pedSize, numAffected,
    subPops=AllAvail, idField='ind_id', fatherField='father_id', motherField='mother_id'):
    '''Draw three-generation families from a population. Such families consist
    of grant parents, their children, spouse of these children, and grand
    children. Number of offspring, total number of individuals, and total
    number of affected individuals in a pedigree should be specified using
    parameters ``numOffspring``, ``pedSize`` and ``numAffected``, which can all
    be a single number, or a range ``[a, b]`` (``b`` is incldued). If a single
    ``families`` is given, pedigrees are drawn randomly from the whole
    population or from specified (virtual) subpopulations (parameter
    ``subPops``). Otherwise, a list of numbers should be used to specify
    numbers of families from each subpopulation, which can be all
    subpopulations if ``subPops=AllAvail`` (default), or from each of the
    specified (virtual) subpopulations. This function returns a population that
    contains extracted individuals.
    '''
    return threeGenFamilySampler(families, numOffspring, affectedParents,
        affectedOffspring, subPops, idField, fatherField, motherField).drawSample(pop)
 

def DrawThreeGenFamilySamples(pop, families, numOffspring, pedSize, numAffected,
    times=1, subPops=AllAvail, idField='ind_id', fatherField='father_id',
    motherField='mother_id'):
    '''Draw ``times`` three-generation pedigree samples from population ``pop``
    and return a list of populations. Please refer to function
    ``DrawThreeGenFamilySample`` for a description of other parameters.
    '''
    return threeGenFamilySampler(families, numOffspring, pedSize, numAffected,
        subPops, idField, fatherField, motherField).drawSamples(pop, times)


class combinedSampler(baseSampler):
    '''A combined sampler accepts a list of sampler objects, draw samples and
    combine the returned sample into a single population. An id field is
    required to use this sampler, which will be used to remove extra copies of
    individuals who have been drawn by different samplers.
    '''
    def __init__(self, samplers=[], idField='ind_id'):
        '''
        samplers
            A list of samplers
        '''
        _sample.__init__(self, *args, **kwargs)
        self.samplers = samplers
        self.idField = idField

    def drawSample(self, pop):
        for s in self.samplers:
            if s.pop is None:
                s.prepareSample(pop)
        #
        samples = [s.drawSample(pop) for s in self.samplers]
        # get IDs
        IDs = []
        for s in samples:
            for gen in range(s.ancestralGens() + 1):
                s.useAncestralGen(gen)
                IDs.extend(s.indInfo(self.idField))
        # extract these guys
        return pop.extract(IDs = IDs, idField = self.idField)


def DrawCombinedSample(pop, samplers, idField='ind_id'):
    '''Draw different types of samples using a list of ``samplers``. A
    population consists of all individuals from these samples will
    be returned. An ``idField`` that stores an unique ID for all individuals
    is needed to remove duplicated individuals who are drawn multiple
    times from these samplers.
    '''
    return combinedSampler(samplers, idField=idField).drawSample(pop)

def DrawCombinedSamples(pop, samplers, times=1, idField='ind_id'):
    '''Draw combined samples ``times`` times and return a list of populations.
    Please refer to function ``DrawCombinedSample`` for details about
    parameters ``samplers`` and ``idField``.
    '''
    return combinedSampler(samplers, idField=idField).drawSamples(pop, times)

