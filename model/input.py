# -*- coding: utf-8 -*-

from .node import Node

class Input(Node):
    def __init__(self, raw_dict=None):
        
        self.raw_dict = raw_dict
        super(Input, self).__init__(raw_dict=raw_dict)

    def build_tensorflow_model(self, model, source1, source2):
        pass

    @staticmethod
    def parse_feature_model(feature_model):

        input = feature_model.get("children")[0] 
        input_type = Node.get_type(input)
        input_element = None

        if(input_type=="zeros"):
            input_element = ZerosInput(raw_dict=input)
        elif(input_type=="identity"):
            input_element = IdentityInput(raw_dict=input)
        elif(input_type=="dense"):
            activation = None
            features = None

            for child in input.get("children"):
                element_type = Node.get_type(child)
                if(element_type == "activation"):
                    if(len(child.get("children"))):
                        activation = Node.get_type(child.get("children")[0])

                elif(element_type == "features"):
                    if(len(child.get("children"))):
                        features = Node.get_type(child.get("children")[0])

            input_element = DenseInput(_features=features,_activation=activation,raw_dict=input)

        elif(input_type=="pooling"):
            _kernel = None
            _stride = None
            _type = None
            _padding = None

            for child in input.get("children"):
                element_type = Node.get_type(child)
                if(element_type == "padding"):
                    if(len(child.get("children"))):
                        _padding = Node.get_type(child.get("children")[0])

                elif(element_type == "type"):
                    if(len(child.get("children"))):
                        _type = Node.get_type(child.get("children")[0])

                elif(element_type == "stride"):
                    if(len(child.get("children"))):
                        _stride = Node.get_type(child.get("children")[0])
                        _stride = _stride.split("x")
                        if len(_stride)==2:
                            _stride = tuple(_stride)
                        else:
                            _stride = None

                elif(element_type == "kernel"):
                    if(len(child.get("children"))):
                        _kernel = Node.get_type(child.get("children")[0])
                        _kernel = _stride.split("x")
                        if len(_kernel)==2:
                            _kernel = tuple(_kernel)
                        else:
                            _kernel = None


            input_element = PoolingInput(_kernel=_kernel,_stride=_stride, _type=_type, _padding=_padding,raw_dict=input)

        elif(input_type=="convolution"):
            _kernel = None
            _stride = None
            _type = None
            _padding = None
            _activation = None
            _features = None

            for child in input.get("children"):
                element_type = Node.get_type(child)
                if(element_type == "padding"):
                    if(len(child.get("children"))):
                        _padding = Node.get_type(child.get("children")[0])

                elif(element_type == "stride"):
                    if(len(child.get("children"))):
                        _stride = Node.get_type(child.get("children")[0])
                        _stride = _stride.split("x")
                        if len(_stride)==2:
                            _stride = tuple(_stride)
                        else:
                            _stride = None

                elif(element_type == "kernel"):
                    if(len(child.get("children"))):
                        _kernel = Node.get_type(child.get("children")[0])
                        _kernel = _stride.split("x")
                        if len(_kernel)==2:
                            _kernel = tuple(_kernel)
                        else:
                            _kernel = None

                elif(element_type == "activation"):
                    if(len(child.get("children"))):
                        activation = Node.get_type(child.get("children")[0])

                elif(element_type == "features"):
                    if(len(child.get("children"))):
                        features = Node.get_type(child.get("children")[0])

            input_element = ConvolutionInput(_kernel=_kernel,_stride=_stride, _padding=_padding,_activation=_activation,_features=_features,raw_dict=input)
        
        return input_element

class ZerosInput(Input):
    def __init__(self, raw_dict=None):
        super(ZerosInput, self).__init__(raw_dict=raw_dict)

class IdentityInput(Input):
    def __init__(self, raw_dict=None):
        super(IdentityInput, self).__init__(raw_dict=raw_dict)

class DenseInput(Input):
    def __init__(self, _features, _activation, raw_dict=None):
        super(DenseInput, self).__init__(raw_dict=raw_dict)

        if not _features:
            self.append_parameter("_features","__int__")

        if not _activation:
            self.append_parameter("_activation","tanh|relu|sigmoid|softmax")


class PoolingInput(Input):
    def __init__(self, _kernel, _stride, _type, _padding, raw_dict=None):
        super(PoolingInput, self).__init__(raw_dict=raw_dict)

        if not _kernel:
            self.append_parameter("_kernel","(__int__,__int__)")

        if not _stride:
            self.append_parameter("_stride",'(__int__,__int__)')

        if not _type:
            self.append_parameter("_type","max|average|dilated|global")

        if not _padding:
            self.append_parameter("_padding","valid|same")


class ConvolutionInput(Input):
    def __init__(self, _kernel, _stride, _features, _padding, _activation, raw_dict=None):
        super(ConvolutionInput, self).__init__(raw_dict=raw_dict)

        if not _kernel:
            self.append_parameter("_kernel","(__int__,__int__)")

        if not _stride:
            self.append_parameter("_stride",'(__int__,__int__)')

        if not _features:
            self.append_parameter("_features","__int__")

        if not _activation:
            self.append_parameter("_activation","tanh|relu|sigmoid|softmax")

        if not _padding:
            self.append_parameter("_padding","valid|same")