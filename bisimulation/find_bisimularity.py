#!/usr/bin/env python

import re

class State(object):
    def __init__(self, name, start_state=False, final_state=False):
        self.name = name
        self.start_state = start_state
        self.final_state = final_state

    def __repr__(self):
        return self.name

class Transition(object):
    def __init__(self, label, start_state, end_state):
        '''
        label is a regex of language inputs that will cause the FSM to
        to this transition
        '''
        self.label = label
        self.start_state = start_state
        self.end_state = end_state

    def __repr__(self):
        return self.start_state.__repr__() + \
               "--" + self.label + "->" + \
               self.end_state.__repr__()

class FSM(object):
    def __init__(self, name, states, transitions):
        self.name = name
        self.states = states
        self.transitions = transitions
    
    @staticmethod
    def merge(first_fsm, second_fsm):
        def rename_fsm(fsm):
            old_state_to_new_state = {}
            for state in fsm.states:
                new_state = State(fsm.name + "_" + state.name,
                                  state.start_state, state.final_state)
                old_state_to_new_state[state] = new_state

            new_states = old_state_to_new_state.values() 

            new_transitions = [Transition(t.label,
                                          old_state_to_new_state[t.start_state],
                                          old_state_to_new_state[t.end_state])
                                for t in fsm.transitions]

            return FSM(fsm.name, new_states, new_transitions)

        renamed_first_fsm = rename_fsm(first_fsm)
        renamed_second_fsm = rename_fsm(second_fsm)

        return FSM("Disjoint Union",
                renamed_first_fsm.states + renamed_second_fsm.states,
                renamed_first_fsm.transitions+ renamed_second_fsm.transitions)

    def __repr__(self):
        return "States: %s, Transitions: %s" % (self.states, self.transitions)

class Bisimulation(object):
    def __init__(self, pairs):
        self.pairs = pairs

    def __repr__(self):
        return str(self.pairs)

# =============================== #

def find_bisimilarity(fsm_a, fsm_b, language):
    '''
    A bisimulation is any relation between States X States, 
    where:

    Whenever xRy,

    if x->x', then \Exists y->y' s.t. x'Ry',

    and

    if y->y', then \Exists x->x' s.t. y'Rx'

    --- 
    The bisimilarity is the (unique) largest bisimulation.

    Note that bisimulation is typically defined on a single FSM.
    Here we compute the bisimulation of the disjoint union of the
    two FSMs.
    
    TODO: figure out how to run this algorithm on two graphs
    TODO: this algorithm isn't the optimal O(NlogN) version
    '''
    union = FSM.merge(fsm_a, fsm_b)
    # To initialize, we start out with three partitions:
    #  { start states, final_states, everything else }
    start_states = set([state for state in union.states if state.start_state])
    final_states = set([state for state in union.states if state.final_state])
    remainders = set(union.states) - start_states - final_states
    # Quotient will contain all equivalence classes of our graph at the end
    quotient = []
    for paritition in [start_states, final_states, remainders]:
        quotient.append(paritition) 

    # We continue "partitioning" the quotient until we're left only with
    # equivalence classes

    # An equivalence class is defined as a set of states where any one of the
    # states can "simulate" any of the other states. That is, suppose I feed a
    # sequence of characters to any one of the states. The state transitions
    # my FSM goes through would be exactly "mirrored" if I had fed the same
    # sequence of characters to any of the other states in the equivalence
    # class.

    # So, our algorithm for finding the bisimilarity proceeds by chopping up
    # the initial paritions. We chop whenever there is a transition from one
    # partiton P to another partition P' such that there are also some
    # transitions leading into P' which do not originate in P. If there are no
    # longer such sets P and P', we know that every remaining partition of the FSM is
    # an equivalence class. TODO: not exactly clear what that means.

    def get_predecessor(fsm, partition, character):
        '''
        The predecessor is defined as the set of states that, when fed the
        label, move into the parition in exactly one transition.
        '''
        # TODO: super inefficient
        predecessor = [transition.start_state
                       for transition in fsm.transitions
                        if transition.start_state not in partition and
                           transition.end_state in partition and
                           re.search(transition.label, character)]
                
        return set(predecessor)

    def choppable_partition(quotient):
        for word in language:
            all_partition_pairs = [(set(p1),set(p2))
                                    for p1 in quotient for p2 in quotient
                                    if p1 != p2]
            for (p1, p2) in all_partition_pairs:
                p2_pred = get_predecessor(union, p2, word)
                intersection = p1.intersection(p2_pred)
                if intersection != p1 and len(intersection) > 0:
                    return (p1, p2_pred)
        
        # If we got here, we're done!
        return None

    choppable = choppable_partition(quotient)
    while choppable:
        (p1, p2_pred) = choppable
        chop1 = p1.intersection(p2_pred)
        chop2 = p1 - p2_pred
        quotient = [partition for partition in quotient if partition != p1]
        quotient += [chop1, chop2]
        choppable = choppable_partition(quotient)

    return quotient

if __name__ == '__main__':
    # The simplest logical view:
    '''
        A /.*/-> Switch /1.2.3.4/-> B
    '''
    
    a = State("A", True, True)
    b = State("B", True, True)
    switch = State("Switch")
    # "ingresss" vs. "egress" is defined wrt the network
    a_ingress = Transition(".*", a, switch)
    b_egress = Transition("1.2.3.4", switch, b)
    logical_network = FSM("Logical", [a,b,switch],
                          [a_ingress,b_egress])

    # A slightly more complicated physical network: 
    '''
        A /.*/-> Switch1 /.*/-> Switch2 /1.2.3.4/-> B
    '''
    switch_1 = State("Switch1")
    switch_2 = State("Switch2")
    # "ingresss" vs. "egress" is defined wrt the network
    a_ingress = Transition(".*", a, switch_1)
    switch_1_to_2 = Transition(".*", switch_1, switch_2)
    b_egress = Transition("1.2.3.4", switch_2, b)
    physical_network = FSM("Physical", [a,b,switch_1,switch_2],
                           [a_ingress,switch_1_to_2,b_egress])

    # Our language is very simple for now 
    language = ["1.2.3.4"]
    print find_bisimilarity(logical_network, physical_network, language)