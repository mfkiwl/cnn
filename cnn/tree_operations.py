from nmigen import *


class TreeStage(Elaboratable):

    def __init__(self, input_w, output_w, num_inputs, n, reg_in, reg_out):
        assert num_inputs % 2 == 0
        self.inputs = [Signal(signed(input_w), name=n+'_input_'+str(i)) for i in range(num_inputs)]
        self.outputs = [Signal(signed(output_w), name=n+'_output_'+str(i)) for i in range(int(num_inputs / 2))]
        self.clken = Signal()
        self.reg_in = reg_in
        self.reg_out = reg_out

    def get_ports(self):
        ports = [self.clken] + self.inputs + self.outputs
        return ports

    @property
    def input_w(self):
        return len(self.inputs[0])

    @property
    def output_w(self):
        return len(self.outputs[0])

    @property
    def latency(self):
        return sum([int(b) for b in (self.reg_in, True, self.reg_out)])

    def elaborate(self, platform):
        m = Module()
        sync = m.d.sync
        comb = m.d.comb
        
        i_dom = sync if self.reg_in else comb
        o_dom = sync if self.reg_out else comb

        input_r = [Signal(signed(self.input_w)) for _ in self.inputs]
        sum_r = [Signal(signed(self.output_w)) for _ in self.outputs]

        _operation = self._operation

        with m.If(self.clken):
            i_dom += [ir.eq(i) for ir, i in zip(input_r, self.inputs)]
            sync += [s.eq(_operation.__call__(input_r[int(2*i)], input_r[int(2*i + 1)])) for i, s in enumerate(sum_r)]
            o_dom += [o.eq(sr) for o, sr in zip(self.outputs, sum_r)]

        return m


class TreeOperation(Elaboratable):
    _operation = None

    def __init__(self, input_w, n_stages, *args, **kwargs):
        class _Stage(TreeStage):
            _operation = self._operation

        self.n_stages = n_stages
        self.clken = Signal()
        self.args = args
        self.kwargs = kwargs
        self.stages = []
        for i in range(n_stages):
            if i == 0:
                stage_input_w = input_w
            else:
                stage_input_w = self.stages[-1].output_w
            stage = _Stage(stage_input_w,
                           self._stage_output_w(stage_input_w),
                           2**(n_stages-i),
                           n='S'+str(i),
                           *args,
                           **kwargs)
            self.stages.append(stage)

        self.inputs = [Signal(signed(input_w), name='input_' + str(i)) for i in range(2**(n_stages))]
        self.output = Signal(signed(self.stages[-1].output_w))
        for i in range(self.num_inputs):
            name = self.inputs[i].name
            setattr(self, self.inputs[i].name, self.inputs[i])

    def get_ports(self):
        ports = [self.clken] + self.inputs + [self.output]
        return ports

    @property
    def input_w(self):
        return len(self.inputs[0])

    @property
    def output_w(self):
        return len(self.output)

    @property
    def num_inputs(self):
        return len(self.inputs)

    @property
    def latency(self):
        return sum(stage.latency for stage in self.stages)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        stages = self.stages

        for i, stage in enumerate(stages):
            m.submodules['tree_oper_' + str(i)] = stage

        # Clock enable to all stages
        comb += [stage.clken.eq(self.clken) for stage in stages]

        # Connect input to first stage
        comb += [stages[0].inputs[i].eq(self.inputs[i]) for i in range(self.num_inputs)]

        # Pipelined stages
        for prv, nxt in zip(stages[0:-1], stages[1:]):
            comb += [nxt_i.eq(prv_o) for prv_o, nxt_i in zip(prv.outputs, nxt.inputs)]

        # Last stage to output
        comb += self.output.eq(stages[-1].outputs[0])

        return m


class TreeAdderUnsigned(TreeOperation):
    _operation = lambda self, a, b: a.as_unsigned() + b.as_unsigned()
    _stage_output_w = lambda self, stage_input_w: stage_input_w + 1

class TreeAdderSigned(TreeOperation):
    _operation = lambda self, a, b: a.as_signed() + b.as_signed()
    _stage_output_w = lambda self, stage_input_w: stage_input_w + 1

class TreeHighestUnsigned(TreeOperation):
    _operation = lambda self, a, b: Mux(a.as_unsigned() > b.as_unsigned(), a, b)
    _stage_output_w = lambda self, stage_input_w: stage_input_w

class TreeLowestSigned(TreeOperation):
    _operation = lambda self, a, b: Mux(a.as_signed() < b.as_signed(), a, b)
    _stage_output_w = lambda self, stage_input_w: stage_input_w

class TreeLowestUnsigned(TreeOperation):
    _operation = lambda self, a, b: Mux(a.as_unsigned() < b.as_unsigned(), a, b)
    _stage_output_w = lambda self, stage_input_w: stage_input_w

class TreeHighestSigned(TreeOperation):
    _operation = lambda self, a, b: Mux(a.as_signed() > b.as_signed(), a, b)
    _stage_output_w = lambda self, stage_input_w: stage_input_w
