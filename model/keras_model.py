# -*- coding: utf-8 -*-
""""""
from __future__ import absolute_import, division, print_function, unicode_literals
import tensorflow as tf
import keras.backend as k
from keras.models import Sequential, Model
from keras.layers import Dense, Flatten
from keras.layers import Input, GlobalAveragePooling2D
from keras.optimizers import SGD
#from keras import optimizers

from keras.utils import multi_gpu_model
from .block import Block
from .output import Out
from .cell import Cell

import random


class KerasFeatureVector(object):

    features = []
    attributes = [0,0,0,0]
    accuracy = None

    def __init__(self, accuracy, attributes, features):
        self.features = features
        self.attributes = attributes
        self.accuracy= accuracy

    def mutate(self, rate=0.05):
        l = len(self.features)
        mask = [random.random() > rate for _ in range(l)]
        self.features = [self.features[i]  if mask[i] else 1 - self.features[i] for i in range(l)]   
 
    def cross_over(self, second_vector, crossover_type="onepoint"):
        if crossover_type=="onepoint":
            point = random.randint(0, len(self.features))
            return KerasFeatureVector(0, [0,0, 0, 0], self.features[0:point]+second_vector.features[point:])

    def to_vector(self):
        return [self.accuracy]+ [self.attributes] + self.features

    @staticmethod
    def from_vector(vect):
        return KerasFeatureVector(vect[0], vect[1], vect[2:])

    def __str__(self):
        return "{}:{}".format(";".join([str(i) for i in self.attributes]), self.accuracy)

    @property
    def fitness(self):
        return 0 if self.accuracy is None else self.accuracy 

class KerasFeatureModel(object):
    
    blocks = []
    outputs = []
    optimizers = []
    features = []
    features_label=  []
    nb_flops  = 0
    nb_params = 0
    model = None
    accuracy = 0

    losss = ['categorical_crossentropy']


    def __init__(self, name=""):
        self._name = name

    def get_custom_parameters(self):
        params = {}
               
        for block in self.blocks:
            params = {**params, **block.get_custom_parameters()}

        return params

    
    def to_kerasvector(self):
        if self.model:
            nb_layers = len(self.model.layers)
        else:
            nb_layers = 0
            
        return KerasFeatureVector(self.accuracy, [len(self.blocks),nb_layers, self.nb_params, self.nb_flops], self.features)

        
    def build(self, input_shape, output_shape, max_parameters=20000000):
        self.outputs = []

        X_input = Input(input_shape)
        _inputs = [X_input]
        model = None

        lr=1.e-2
        n_steps=20
        global_step = tf.Variable(0)    
        global_step=1
        learning_rate = tf.train.cosine_decay(
            learning_rate=lr,
            global_step=global_step,
            decay_steps=n_steps
        )
        self.optimizers.append(SGD(lr=0.1, momentum=0.9, decay=0.0001, nesterov=True))
        self.optimizers = [ "sgd", tf.train.RMSPropOptimizer(learning_rate=learning_rate)]
        
        try:
            print("Build Tensorflow model")
            for block in self.blocks:
                _inputs, _outputs = block.build_tensorflow_model(_inputs)
                self.outputs = self.outputs + _outputs

            out = self.outputs[-1] if len(self.outputs) else  _inputs[0]
            out = out.content if hasattr(out,"content") else out

            if out.shape.ndims >2:
                out = Flatten()(out)
                #out = GlobalAveragePooling2D()(out)
            self.outputs = [Dense(output_shape, activation="softmax", name="out")(out)]
            # Create model

            #with tf.device('/cpu:0'):
            model = Model(outputs=self.outputs, inputs=X_input,name=self._name)

            #sgd = optimizers.SGD(lr=0.01, decay=1e-6, momentum=0.9, nesterov=True)

            if model.count_params() > 20000000:
                print("#### model is bigger than 20M params. Skipped")
                model.summary()
                return None 

            try:
                model = multi_gpu_model(model, gpus=4)
            except:
                print("multi gpu not available")

            print("Compile Tensorflow model with loss:{}, optimizer {}".format(self.losss[0], self.optimizers[0]))
            model.compile(loss=self.losss[0], metrics=['accuracy'], optimizer=self.optimizers[0])
        
        except Exception as e:
            import traceback
            print("error",e)
            print (traceback.format_exc())
            
            if model:
                model.summary()
            return None
        
        self.model = model
        return model


    @staticmethod
    def parse_feature_model(feature_model, name=None, depth=1, product_features=None, features_label=None):

        print("building keras model from feature model tree")
        model = KerasFeatureModel(name=name)

        if product_features:
            #sorted_features = sorted( product_features, key=lambda k: abs(int(k)))
            model.features = [1 if str(x).isdigit() and int(x)>0 else 0 for x in product_features]
        
        if features_label:
            model.features_label = features_label

        model.blocks = []

        if len(feature_model)==0:
            return model

        if isinstance(feature_model, str):
            model.blocks = KerasFeatureModel.get_from_template(feature_model)

        else: 
            for i in range(depth):
                for block_dict in feature_model:
                    block_dict["children"] = reversed(block_dict["children"])
                    block = Block.parse_feature_model(block_dict)
                    model.blocks.append(block)

            model.blocks.sort(key = lambda a : a.get_name())

            missing_params = model.get_custom_parameters()
            for name,(node, params) in missing_params.items():
                print("{0}:{1}".format(name, params))

        return model


    @staticmethod
    def get_from_template(feature_model):
        blocks = []
        if feature_model=="lenet5":
            from .leNet import lenet5_blocks
            blocks =  lenet5_blocks()
        
        return blocks