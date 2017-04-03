"""A tool to generate pipelined logic from expressions"""
import subprocess
from math import ceil, log
import math


class Component:
    """A component is a container object to which inputs, outputs,
    combinational logic and registers may be added."""

    def __init__(self):
        self.inputs, self.outputs, self.streams, self.registers = [], [], [], []
        self.sn = 0

    def generate(self, name):

        #align outputs
        max_offset = max([i.stream.offset for i in self.outputs])
        delays = [(not i.stream.constant) and 
                max_offset - i.stream.offset for i in self.outputs]

        for i, d in zip(self.outputs, delays):
            if d:
                i.stream = Register(i.stream, d)
                i.stream.add_to_component(self)

        for i in self.outputs:
            i.stream.add_to_component(self)

        return "".join([
        "module dq (clk, q, d);\n",
        "  input  clk;\n",
        "  input  [width-1:0] d;\n",
        "  output [width-1:0] q;\n",
        "  parameter width=8;\n",
        "  parameter depth=2;\n",
        "  integer i;\n",
        "  reg [width-1:0] delay_line [depth-1:0];\n",
        "  always @(posedge clk) begin\n",
        "    delay_line[0] <= d;\n",
        "    for(i=1; i<depth; i=i+1) begin\n",
        "      delay_line[i] <= delay_line[i-1];\n",
        "    end\n",
        "  end\n",
        "  assign q = delay_line[depth-1];\n",
        "endmodule\n\n",
        "module %s(clk, "%name,
        ", ".join(["%s"%i.iname for i in self.inputs+self.outputs]),
        ");\n",
        "  input clk;\n",
        "".join(["  input [%s:0] %s;\n"%(i.bits-1, i.iname) 
            for i in self.inputs]),
        "".join(["  output [%s:0] %s;\n"%(i.bits-1, i.iname) 
            for i in self.outputs]),
        "".join(["  wire [%s:0] %s;\n"%(i.bits-1, i.name) 
            for i in self.streams]),
        "\n",
        "".join([i.generate()+"\n" for i in self.streams+self.outputs]),
        "endmodule\n"])


    def test(self, stimulus, name="uut", debug=False):
        latency = max([i.stream.offset for i in self.outputs])
        stimulus_length = max([len(i) for i in stimulus.values()])
        stop_clocks = stimulus_length + latency + 1

        for n, s in stimulus.iteritems():
            f = open("stim/"+n, 'w')
            f.write("".join(["%d\n"%i for i in s]))
            f.close()

        if debug:
            debug = '    $dumpfile("test.vcd");\n    $dumpvars(0,uut_tb);\n'
        else:
            debug = ''

        testbench = "".join([
        "module %s_tb;\n"%name,
        "  reg clk;\n",
        "".join(["  reg [%s:0] %s;\n"%(i.bits-1, i.iname) 
            for i in self.inputs]),
        "".join(["  wire [%s:0] %s;\n"%(i.bits-1, i.iname) 
            for i in self.outputs]),
        "".join(["  integer %s_file;\n"%(i.iname) for i in self.inputs]),
        "".join(["  integer %s_file;\n"%(i.iname) for i in self.outputs]),
        "".join(["  integer %s_count;\n"%(i.iname) for i in self.inputs]),
        "".join(["  integer %s_count;\n"%(i.iname) for i in self.outputs]),
        "\n",
        "  %s %s1 (clk, %s);\n"%(name, name, ", ".join([i.iname 
            for i in self.inputs+self.outputs])),
        "  initial\n",
        "  begin\n",
        debug,
        "".join(['    %s_file = $fopen("stim/%s");\n'%(i.iname, i.iname) 
            for i in self.outputs]),
        "".join(['    %s_file = $fopen("stim/%s", "r");\n'%(i.iname, i.iname) 
            for i in self.inputs]),
        "  end\n\n",
        "  initial\n",
        "  begin\n",
        "    #%s $finish;\n" % (10 * stop_clocks),
        "  end\n\n",
        "  initial\n",
        "  begin\n",
        "    clk <= 1'b0;\n",
        "    while (1) begin\n",
        "      #5 clk <= ~clk;\n",
        "    end\n",
        "  end\n\n",
        "  always @ (posedge clk)\n",
        "  begin\n",
        "".join(['    $fdisplay(%s_file, "%%d", %s);\n'%(i.iname, i.iname) 
            for i in self.outputs]),
        "".join([
            '    #0 %s_count = $fscanf(%s_file, "%%d\\n", %s);\n'%(
                i.iname, i.iname, i.iname) for i in self.inputs]),
        "  end\n",
        "endmodule\n"])

        f = open("%s.v"%name, 'w')
        f.write(self.generate(name))
        f.close()

        f = open("%s_tb.v"%name, 'w')
        f.write(testbench)
        f.close()

        subprocess.call(["iverilog", "-o", "%s_tb"%name, "%s.v"%name, "%s_tb.v"%name])
        subprocess.call(["vvp", "%s_tb"%name])

        response = {}
        for i in self.outputs:
            f = open("stim/"+i.iname)
            response[i.iname] = [int(j) for j in list(f)[1+latency:]]
            f.close()
        return response


class Stream:
    """A stream is a base class from which other expression classes are
    derived, all streams have a name, bits and constant property"""

    def __init__(self, bits, offset, sources):
        """This constructor will usually be called by a derived object class"""

        self.bits, self.offset = bits, offset
        self.constant = False
        self.added = False
        self.sources = sources

    def add_to_component(self, component):
        if not self.added:
            self.name = "s_"+str(component.sn)
            component.sn += 1
            component.streams.append(self)
            for source in self.sources:
                source.add_to_component(component)
            self.added = True

    def __add__(self, other):
        return add(self, other)
    def __sub__(self, other):
        return sub(self, other)
    def __mul__(self, other):
        return mul(self, other)
    def __gt__(self, other):
        return gt(self, other)
    def __ge__(self, other):
        return ge(self, other)
    def __lt__(self, other):
        return lt(self, other)
    def __le__(self, other):
        return le(self, other)
    def __eq__(self, other):
        return eq(self, other)
    def __ne__(self, other):
        return ne(self, other)
    def __lshift__(self, other):
        return sl(self, other)
    def __rshift__(self, other):
        return sr(self, other)
    def __and__(self, other):
        return band(self, other)
    def __or__(self, other):
        return bor(self, other)
    def __xor__(self, other):
        return bxor(self, other)
    def __abs__(self):
        return select(self, -self, self>=0)
    def __neg__(self):
        return negate(self)
    def __invert__(self):
        return invert(self)
    def __getitem__(self, other):
        try:
            return getbit(self, int(other))
        except TypeError:
            return getbits(self, other.start, other.stop)
    def __floordiv__(self, other):
        return divide(self, other)[0]
    def __mod__(self, other):
        return divide(self, other)[1]


class Input(Stream):
    """An input to the component."""

    def __init__(self, component, bits, iname):
        """add an output to component
        arguments:
            bits, the width of the input in bits
            iname, the name of the input"""

        Stream.__init__(self, bits, 0, [])
        self.iname = iname
        component.inputs.append(self)

    def generate(self):
        return "  assign %s = %s;"%(self.name, self.iname)

class Output:
    """An output of the component."""

    def __init__(self, component, oname, stream):
        """add an output to component
        arguments:
            iname, the name of the input
            stream, the expression to be output"""
        stream = const(stream)
        self.iname, self.bits, self.stream = oname, stream.bits, stream
        component.outputs.append(self)

    def generate(self):
        return "  assign %s = %s;"%(self.iname, self.stream.name)

def number_of_bits_needed(x):
    if x > 0:
        n = 1
        while 1:
            max_number = 2**n-1
            if max_number >= x:
                return n
            n+=1
    elif x < 0:
        x = -x
        n = 1
        while 1:
            max_number = 2**(n-1)
            if max_number >= x:
                return n
            n+=1
    else:
        return 1


def const(i):
    if isinstance(i, Stream):
        return i

    bits = number_of_bits_needed(i)
    return Constant(bits, int(i))

class Constant(Stream):
    """A constant value"""

    def __init__(self, bits, value):
        """a constant value
        arguments:
            bits - the width of the constant in bits
            value - the value of the constant (must be convertible to an int)"""
        Stream.__init__(self, bits, 0, [])
        self.value = int(value)
        self.constant = True

    def generate(self):
        if self.value >= 0:
            return "  assign %s = %s'd%s;"%(self.name, self.bits, self.value) 
        else:
            return "  assign %s = -%s'd%s;"%(self.name, self.bits, -self.value) 

class Register(Stream):
    """A register.
    Balancing registers will be placed on other paths, so a register
    has the effect of breaking a timing path, and increasing latency
    without changing the meaning of an expression."""
    def __init__(self, i, delay = 1):
        """a register
        arguments:
            bits - the width of the constant in bits
            delay=1 - the number of clock cycles latency"""

        i = const(i)
        Stream.__init__(self, i.bits, i.offset+delay, [i])
        self.i, self.delay = i, delay

    def generate(self):
        return "  dq #(%s, %s) dq_%s (clk, %s, %s);"%(
            self.bits, int(self.delay), self.name, self.name, self.i.name)

class Combinational(Stream):
    """A combinational logic expression

    This class serves as template for logic expressions, the following
    templates are defined:

    add, sub, mul, gt, ge, lt, le, eq, ne, band, bor, bxor, bnot, select,
    index, getbits, getbit, cat"""
    def __init__(self, inputs, bits, code):
        """a combinational logic template
        arguments:
            inputs - a list of inputs
            bits - width of expression in bits
            code - code template"""
        inputs = [const(i) for i in inputs]
        max_delay = max([i.offset for i in inputs])
        delays = [(not i.constant) and max_delay - i.offset for i in inputs]
        self.code = code
        self.inputs = [(Register(i, int(d)) if d else i) 
                for i, d in zip(inputs, delays)]
        Stream.__init__(self, bits, max_delay, self.inputs)

    def generate(self):
        return "".join(self.code.format(*([self.name] + [i.name 
            for i in self.inputs])))

def add(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], max([x.bits, y.bits]), 
            "  assign {0} = {1} + {2};")
def sub(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], max([x.bits, y.bits]), 
            "  assign {0} = {1} - {2};")
def mul(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], max([x.bits, y.bits]), 
            "  assign {0} = {1} * {2};")
def sr(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], max([x.bits, y.bits]), 
            "  assign {0} = {1} >> {2};")
def sl(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], max([x.bits, y.bits]), 
            "  assign {0} = {1} << {2};")
def gt(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], 1, '  assign {0} = {1} > {2};')
def ge(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], 1, '  assign {0} = {1} >= {2};')
def lt(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], 1, '  assign {0} = {1} < {2};')
def le(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], 1, '  assign {0} = {1} <= {2};')
def s_mul(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], max([x.bits, y.bits]), 
            "  assign {0} = $signed({1}) * $signed({2});")
def s_sr(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], max([x.bits, y.bits]), 
            "  assign {0} = $signed({1}) >>> $signed({2});")
def s_sl(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], max([x.bits, y.bits]), 
            "  assign {0} = $signed({1}) <<< $signed({2});")
def s_gt(x, y):
    return Combinational([x, y], 1, 
            '  assign {0} = $signed({1}) > $signed({2});')
def s_ge(x, y):
    return Combinational([x, y], 1, 
            '  assign {0} = $signed({1}) >= $signed({2});')
def s_lt(x, y):
    return Combinational([x, y], 1, 
            '  assign {0} = $signed({1}) < $signed({2});')
def s_le(x, y):
    return Combinational([x, y], 1, 
            '  assign {0} = $signed({1}) <= $signed({2});')
def eq(x, y):
    return Combinational([x, y], 1, '  assign {0} = {1} == {2};')
def ne(x, y):
    return Combinational([x, y], 1, '  assign {0} = {1} != {2};')
def band(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], max(x.bits, y.bits), 
            '  assign {0} = {1} & {2};')
def bor(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], max(x.bits, y.bits), 
            '  assign {0} = {1} | {2};')
def bxor(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], max(x.bits, y.bits), 
            '  assign {0} = {1} ^ {2};')
def invert(x):
    x = const(x)
    return Combinational([x], x.bits, "  assign {0} = ~{1};")
def negate(x):
    x = const(x)
    return Combinational([x], x.bits, "  assign {0} = -{1};")
def select(x, y, z):
    x, y = const(x), const(y)
    return Combinational([x, y, z], max(x.bits, y.bits), 
            "  assign {0} = {3}?{1}:{2};")
def index(x, y):
    return Combinational([x, y], 1, "  assign {0} = {1}[{2}];")
def getbits(x, y, z):
    return Combinational([x], y-z+1, 
            "  assign {0} = {1}[%s:%s];"%(int(y), int(z)))
def getbit(x, y):
    return Combinational([x], 1, "  assign {0} = {1}[%s];"%int(y))
def setbits(x, y, z):
    x = const(x)
    return Combinational([x], x.bits, 
            "  assign {0} = {{{0}[%s:%s],{1},{0}[%s:%s]}}};"%(
                x.bits-1, int(y)+1, int(z)-1, 0))
def setbit(x, y):
    return Combinational([x], 1, 
            "  assign {0} = {{{0}[%s:%s],{1},{0}[%s:%s]}};"%(
                x.bits-1, int(y)+1, int(y)-1, 0))
def resize(x, y):
    return Combinational([x], y, 
            "  assign {0} = {1};")
def s_resize(x, y):
    return Combinational([x], y, "  assign {0} = $signed({1});")
def cat(x, y):
    x, y = const(x), const(y)
    return Combinational([x, y], x.bits+y.bits, "  assign {0} = {{{1},{2}}};")
def divide(dividend, divisor):
    bits = max([dividend.bits, divisor.bits])
    remainder = Constant(bits, 0)
    quotient = Constant(bits, 0)
    for i in range(bits):
        shifter = remainder << 1 | dividend[bits-1-i]
        difference = resize(shifter, bits+1) - divisor
        negative = difference[bits]
        remainder = select(shifter, difference, negative)
        quotient = quotient << 1
        quotient = select(quotient, quotient | 1, negative)
        quotient = Register(quotient)
        remainder = Register(remainder)

    return quotient, remainder

def s_divide(dividend, divisor):
    divisor_sign = divisor[divisor.bits-1]
    dividend_sign = dividend[dividend.bits-1]
    sign = dividend_sign, divisor_sign
    quotient, remainder = divide(abs(dividend), abs(divisor))
    quotient = select(-quotient, quotient, sign)
    remainder = select(-remainder, remainder, dividend_sign)
    return quotient, remainder

def sqrt(x):
    bits = x.bits

    largest_number = (2**bits)-1
    largest_sqrt = ceil(math.sqrt(largest_number))
    result_bits = int(ceil(log(largest_sqrt, 2.0)))

    guess = Constant(result_bits, 0)
    guess_squared = Constant(bits+1, 0)

    #Calculate 1 bit at a time from msb to lsb
    #Each bit is set if the guess squared is still less than x
    #
    #Instead of squaring the new guess, calculate the new guess
    #squared from the new bit value using shifts and adds.
    #
    #(guess + 2^bit)^2 <= x
    #guess^2 + 2*guess*2^bit + 2^bit^2 <= x

    for bit in reversed(range(result_bits)):
        new_guess_squared = guess_squared + (guess << (bit+1)) | 1<<bit*2
        better = new_guess_squared <= x
        guess_squared = select(new_guess_squared, guess_squared, better)
        guess = select(guess + Constant(bits, 2**bit), guess, better)

    return guess

def sqrt_rounded(x):
    bits = x.bits
    x = resize(x, x.bits+2)<<2
    x = sqrt(x)
    x += 1
    x >>= 1
    x = x[bits-1:0]
    return x


if __name__ == "__main__":
    a = Input(8, 'a')
    b = Input(8, 'b')
    c = Input(8, 'c')
    Output("z", Register(Register(a, 10)+b)+c)
    print test(component, {'a':range(10), 'b':range(10), 'c':range(10)})
