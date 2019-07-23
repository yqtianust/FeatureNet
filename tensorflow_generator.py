# -*- coding: utf-8 -*-
""""""
from __future__ import absolute_import, division, print_function, unicode_literals
from model.keras_model import KerasFeatureModel
from keras.datasets import mnist, cifar10, cifar100
import keras
from keras import backend as K
import tensorflow as tf
from keras.backend.tensorflow_backend import set_session
from keras.backend.tensorflow_backend import clear_session
from keras.backend.tensorflow_backend import get_session
import json
import time
from keras.callbacks import Callback, EarlyStopping, LearningRateScheduler, ReduceLROnPlateau,ModelCheckpoint
from keras.preprocessing.image import ImageDataGenerator
import numpy as np
from art.classifiers import KerasClassifier
from model import metrics
from keras.optimizers import Adam

#from keras.utils.training_utils import multi_gpu_model
#from tensorflow.python.client import device_lib


# def get_available_gpus():
#     local_device_protos = device_lib.list_local_devices()
#     return [x.name for x in local_device_protos if x.device_type == 'GPU']

def get_flops():
    run_meta = tf.RunMetadata()
    opts = tf.profiler.ProfileOptionBuilder.float_operation()

    # We use the Keras session graph in the call to the profiler.
    flops = tf.profiler.profile(graph=K.get_session().graph,
                                run_meta=run_meta, cmd='op', options=opts)

    return flops.total_float_ops

def lr_schedule(epoch):
    """Learning Rate Schedule

    Learning rate is scheduled to be reduced after 80, 120, 160, 180 epochs.
    Called automatically every epoch as part of callbacks during training.

    # Arguments
        epoch (int): The number of epochs

    # Returns
        lr (float32): learning rate
    """
    lr = 1e-3
    if epoch > 180:
        lr *= 0.5e-3
    elif epoch > 160:
        lr *= 1e-3
    elif epoch > 120:
        lr *= 1e-2
    elif epoch > 80:
        lr *= 1e-1
    #print('Learning rate: ', lr)
    return lr
    
def reset_keras():
    sess = get_session()
    clear_session()
    sess.close()

    # use the same config as you used to create the session
    config = tf.ConfigProto() #allow_soft_placement=True, log_device_placement=True)
    set_session(tf.Session(config=config))

class TimedStopping(Callback):
    '''Stop training when enough time has passed.
    # Arguments
        seconds: maximum time before stopping.
        verbose: verbosity mode.
    '''
    def __init__(self, generator,epoch_seconds=None, total_seconds=None, verbose=0):
        super(TimedStopping, self).__init__()

        self.start_time = 0
        self.epoch_seconds = epoch_seconds
        self.total_seconds = total_seconds
        self.verbose = verbose
        self.generator = generator

    def on_train_begin(self, logs={}):
        self.start_time = time.time()

    def on_epoch_begin(self, epoch, logs={}):
        self.start_epoch = time.time()

    def on_epoch_end(self, epoch, logs={}):
        if self.total_seconds and time.time() - self.start_time > self.total_seconds:
            self.generator.stop_training=self.model.stop_training = True
            if self.verbose:
                print('Stopping after total time reached %s seconds.' % self.total_seconds)

        if self.epoch_seconds and time.time() - self.start_epoch > self.epoch_seconds:
            self.generator.stop_training=self.model.stop_training = True
            if self.verbose:
                print('Stopping after epoch time reached %s seconds.' % self.epoch_seconds)
        

class TensorflowGenerator(object):
    model_graph = ""
    accuracy = 0
    training_time = 0
    params = 0
    flops = 0
    stop_training = False
    X_train = []
    Y_train = []
    X_test = []
    Y_test = []
    history = ([],[])
    dataset = None
    input_shape = (0,0,0)
    default_batchsize = 64
    num_classes = 10
    default_robustness_set_size = 100 #500

    model_graph_export = True
    
    datasets_classes = {"mnist":10,"cifar":10,"cifar100":100}

    def __init__(self, product, epochs=12, dataset="mnist", data_augmentation = False, depth=1, product_features=None, features_label=None, no_train=False,clear_memory=True, batch_size=128, eval_robustness=None, save_path=None, robustness_set_size=0):
        #product_features is a list of enabled and disabled features based on the original feature model
        
        if batch_size ==0:
            batch_size = TensorflowGenerator.default_batchsize
            
        if product:
            self.model =KerasFeatureModel.parse_feature_model(product, name="", depth=depth, product_features=product_features, features_label=features_label)

            print("====> Loading new feature model with {0} blocks".format(len(self.model.blocks)))
            model = TensorflowGenerator.build(self.model, dataset, clear_memory=clear_memory)
            
            if not model:
                print("#### model is not valid ####")
                return 
            
            if no_train:
                self.print()
                return  

            if save_path:
                save_path = "{}{}".format(save_path,self.model._name)
                
            history, training_time, score = TensorflowGenerator.train(self.model, epochs, batch_size, data_augmentation,dataset, save_path=save_path)
            
            if eval_robustness:
                TensorflowGenerator.eval_robustness(self.model, eval_robustness, robustness_set_size)

            self.params = self.model.nb_params
            self.training_time = training_time
            self.accuracy = self.model.accuracy
            self.history = (history.history['acc'], history.history['val_acc'])

    @staticmethod
    def eval_attack_robustness(keras_model, attack_name, norm, robustness_set_size=0):
        
        attack_params = {"norm":norm}

        if attack_name=="cw":
            attack_params["targeted"] = False;
        elif attack_name=="pgd":
             attack_params["eps_step"] = 0.1
             attack_params["eps"]= 1.
        
        if robustness_set_size==0:
            adv_set = TensorflowGenerator.X_robustness
        else:
            adv_set = TensorflowGenerator.X_test[0:min(len(TensorflowGenerator.X_test), robustness_set_size)]
            
        return float(metrics.empirical_robustness(keras_model,adv_set,attack_name, attack_params))

    @staticmethod
    def eval_robustness(model, scores=[], robustness_set_size=0):
        keras_model = model.model
        if not keras_model:
            return 
        begin_robustness = time.time() 
        try:
            norm = 2
            r_l1 = 40
            r_l2 = 2
            r_li = 0.1
            nb_batches = 10
            batch_size = 5
            radius = r_l1 if norm==1 else (r_l2 if norm==2 else r_li)
            
            keras_model = KerasClassifier(model=keras_model, clip_values=(0, 255))

            score_metrics = model.robustness_scores if not scores else scores
           
            if "clever" in score_metrics:
                if robustness_set_size==0:
                    x_set = TensorflowGenerator.X_robustness
                else:
                    x_set = TensorflowGenerator.X_test[0:robustness_set_size]
                scores = []
                for element in x_set:
                    score = metrics.clever_u(keras_model, element, nb_batches, batch_size, radius, norm=norm, pool_factor=3)
                    scores.append(score)
                model.clever_score = np.average(scores)
            if "pgd" in score_metrics:
                model.pgd_score = TensorflowGenerator.eval_attack_robustness(keras_model, "pgd", norm,robustness_set_size)
            if "cw" in score_metrics:
                model.cw_score = TensorflowGenerator.eval_attack_robustness(keras_model, "cw", norm,robustness_set_size)
            if "fgsm" in score_metrics:
                model.fgsm_score = TensorflowGenerator.eval_attack_robustness(keras_model, "fgsm", norm,robustness_set_size)
            
        except Exception as e:
            import traceback
            print("error",e)
            print (traceback.format_exc())
        
        robustness_time = time.time() - begin_robustness
        model.robustness_score = getattr(model,"{}_score".format(scores[0]),0) if len(scores) else model.clever_score
        print('model robustness (clever, pgd, cw, fgsm): {} time:{}'.format((model.clever_score,model.pgd_score, model.cw_score, model.fgsm_score),robustness_time))

    @staticmethod
    def build(model, dataset, clear_memory=True):

        if clear_memory:
            reset_keras()

        TensorflowGenerator.init_dataset(dataset)
        keras_model =  model.build(TensorflowGenerator.input_shape, TensorflowGenerator.datasets_classes.get(dataset))

        if not keras_model:
            return keras_model

        optimizers = [  Adam(lr=lr_schedule(0)), "sgd"]
        losss = ['categorical_crossentropy']
        #print("Compile Tensorflow model with loss:{}, optimizer {}".format(losss[0], optimizers[0]))
        keras_model.compile(loss=losss[0], metrics=['accuracy'], optimizer=optimizers[0])

        model.nb_params =  keras_model.count_params()
        print('model blocks,layers,params,flops: {} '.format(model.to_kerasvector()))

        return keras_model


    @staticmethod
    def train(model, epochs, batch_size, data_augmentation, dataset, save_path=None):

        keras_model = model.model
        begin_training = time.time()    
            
        early_stopping = EarlyStopping(monitor='val_acc', mode='max', min_delta=0.005, patience=100)
        #early_stopping = EarlyStopping(monitor='val_loss', mode='min', patience=10)
        
        lr_scheduler = LearningRateScheduler(lr_schedule)
        
        timed = TimedStopping(model,None, 6000)
        lr_reducer = ReduceLROnPlateau(factor=np.sqrt(0.1),
                            cooldown=0,
                            patience=5,
                            min_lr=0.5e-6)
                            
        callbacks=[timed, early_stopping, lr_reducer, lr_scheduler]

        if save_path:
            model_path = "{}.h5".format(save_path)
            mc = ModelCheckpoint(model_path, monitor='val_loss', mode='min', save_best_only=True)
            callbacks.append(mc)
        
        #print("training with batch size {} epochs {} callbacks {} dataset {} data-augmentation {}".format(batch_size,epochs, callbacks,dataset , data_augmentation))
        
        history = keras_model.fit(TensorflowGenerator.X_train, TensorflowGenerator.Y_train,
                batch_size=batch_size,
                epochs=epochs,
                verbose=2,
                validation_data=(TensorflowGenerator.X_test, TensorflowGenerator.Y_test), 
                callbacks=callbacks)

        training_time = time.time() - begin_training

        score = keras_model.evaluate(TensorflowGenerator.X_test, TensorflowGenerator.Y_test, verbose=0)
        
        #model.nb_flops = get_flops()
        model.accuracy =score[1]
        
        print('Test loss: {} Test accuracy: {} training_time {}'.format(score[0],  score[1], training_time))
        
        return history, training_time, score

    @staticmethod
    def init_dataset(dataset, data_augmentation=False):
        TensorflowGenerator.num_classes = 10

        if TensorflowGenerator.dataset != dataset:

            # the data, split between train and test sets
            if dataset=="mnist":
                (x_train, y_train), (x_test, y_test) = mnist.load_data()
            elif dataset=="cifar":
                (x_train, y_train), (x_test, y_test) = cifar10.load_data()
            elif dataset=="cifar100":
                (x_train, y_train), (x_test, y_test) = cifar100.load_data()
                TensorflowGenerator.num_classes = 100

            # input image dimensions
            img_rows, img_cols, channels = x_train.shape[1], x_train.shape[2], x_train.shape[3] if len(x_train.shape) ==4 else 1

            # convert class vectors to binary class matrices
            y_train = keras.utils.to_categorical(y_train, TensorflowGenerator.num_classes)
            y_test = keras.utils.to_categorical(y_test, TensorflowGenerator.num_classes)

            if K.image_data_format() == 'channels_first':
                x_train = x_train.reshape(x_train.shape[0], channels, img_rows, img_cols)
                x_test = x_test.reshape(x_test.shape[0], channels, img_rows, img_cols)
                TensorflowGenerator.input_shape = (channels, img_rows, img_cols)
            else:
                x_train = x_train.reshape(x_train.shape[0], img_rows, img_cols, channels)
                x_test = x_test.reshape(x_test.shape[0], img_rows, img_cols, channels)
                TensorflowGenerator.input_shape = (img_rows, img_cols, channels)

            x_train = x_train.astype('float32')
            x_test = x_test.astype('float32')
            x_train /= 255
            x_test /= 255
            #print('x_train shape:', x_train.shape)
            #print(x_train.shape[0], 'train samples')
            #print(x_test.shape[0], 'test samples')

            if data_augmentation:

                augment_size=5000
                train_size = x_train.shape[0]

                datagen = ImageDataGenerator(
                rotation_range=10,
                zoom_range = 0.05, 
                width_shift_range=0.07,
                height_shift_range=0.07,
                horizontal_flip=False,
                vertical_flip=False, 
                data_format="channels_last",
                zca_whitening=True)

                # compute quantities required for featurewise normalization
                # (std, mean, and principal components if ZCA whitening is applied)
                datagen.fit(x_train, augment=True)

                randidx = np.random.randint(train_size, size=augment_size)
                x_augmented = x_train[randidx].copy()
                y_augmented = y_train[randidx].copy()
                
                x_augmented = datagen.flow(x_augmented, np.zeros(augment_size), batch_size=augment_size, shuffle=False).next()[0]
                x_train = np.concatenate((x_train, x_augmented))
                y_train = np.concatenate((y_train, y_augmented))

            TensorflowGenerator.X_train = x_train
            TensorflowGenerator.X_test = x_test
            TensorflowGenerator.Y_train = y_train
            TensorflowGenerator.Y_test = y_test

            TensorflowGenerator.X_robustness = x_test[0:TensorflowGenerator.default_robustness_set_size]
            TensorflowGenerator.Y_robustness = y_test[0:TensorflowGenerator.default_robustness_set_size]

            TensorflowGenerator.dataset = dataset

    @staticmethod
    def export_png(model, path):
        if not TensorflowGenerator.model_graph_export:
            return

        from keras.utils import plot_model
        try:
            plot_model(model, to_file='{}.png'.format(path))
        except Exception as e:
            print(e)
            TensorflowGenerator.model_graph_export = False

    def print(self, include_summary=True, invalid_params=True, export_png=True):
        model = self.model.model
        if include_summary:
            model.summary()
            
        if invalid_params:
            missing_params = self.model.get_custom_parameters()
            for name,(node, params) in missing_params.items():
                print("{0}:{1}".format(name, params))
        
        if TensorflowGenerator.model_graph and export_png:
            TensorflowGenerator.export_png(model, TensorflowGenerator.model_graph)
            
    def load_products(self, product):
        def build_rec(node, level=0):
            #print("-"*level + node.get("label"))
            for child in node.get("children"):
                build_rec(child, level+1)

        build_rec(product)
        

#f = open("./lenet5.json", "r")

#product = json.loads(f.read())

#tensorflow = TensorflowGenerator(product)

