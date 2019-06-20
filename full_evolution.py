import subprocess
import sys
import getopt
import json, pickle
import os
from tensorflow_generator import TensorflowGenerator
from model.keras_model import KerasFeatureVector, KerasFeatureModel
from model.mutation.mutable_base import MutableBase, MutationStrategies
from products_tree import ProductSet, ProductSetError
import random, math
from numpy.random import choice
import numpy as np
import tensorflow
import gc
import datetime
import time
from math import ceil
import re
import copy 
base_path = '../products'
base_training_epochs = 12
evolution_epochs = 50



def reset_keras(classifier=None):
    
    if classifier:
        try:
            del classifier
        except:
            pass

    # if it's done something you should see a number being outputted
    print("cleaning memory {}".format(gc.collect()))

class FullEvolution(object):

    
    @staticmethod
    def select(last_population, survival_count):
        fittest = []
        x =  [e.accuracy for e in last_population]
        e_x = np.exp(x - np.max(x))
        last_population_probability =  e_x / e_x.sum()
        
        for i in range(survival_count):
            individual= choice(last_population, None, last_population_probability.tolist())
            fittest.append(individual)
        
        return fittest

    @staticmethod
    def generate_mutant(parent, mutation_ratio):
        
        nb_max_mutations = 100
        if MutableBase.mutation_stategy==MutationStrategies.CHOICE :
            mutations = np.random.uniform(size=nb_max_mutations)
            nb_mutations = len([e for e in mutations if e<mutation_ratio])
        else:
            nb_mutations = 1
        blocks = parent.dump_blocks()
        blocks = copy.deepcopy(blocks)
        mutant = KerasFeatureModel.parse_blocks(blocks)
        mutant.accuracy = 0

        for j in range(nb_mutations):
            mutant.mutate(mutation_ratio)

        return mutant

        
    @staticmethod
    def train_products(initial_product_set, dataset,training_epochs, max_products=0):
        start = time.time()
        print("### training products for dataset {}: {}".format(
            dataset, datetime.datetime.now()))
        last_population = []
        for index, (product, original_product) in enumerate(initial_product_set.format_products()):
            print("### training product {}".format(index))
            tensorflow = TensorflowGenerator(product, training_epochs, dataset, product_features=original_product, depth=1,
                                            features_label=initial_product_set.features, no_train=False, data_augmentation=False)

            if tensorflow and hasattr(tensorflow,"model") and tensorflow.model:
                last_population.append(tensorflow.model.to_kerasvector())
            reset_keras(tensorflow)

            if max_products>0 and index==max_products:
                break

        end = time.time()
        print("### training products over, took {}s".format(str(end-start)))
        return last_population

    @staticmethod
    def evolve(evo, session_path, nb_product_perparent, dataset, new_pop, training_epochs, mutation_ratio=0.1  ):
        len_pop = len(new_pop)
        mutants = []
        for i in range(len_pop):
            individual1 = new_pop[i]
            print("### generating children of product {}".format(i))
            for i in range(nb_product_perparent): 
                individual2 = choice(new_pop)
                individual = individual1.breed(individual2)
                mutant = FullEvolution.generate_mutant(individual,mutation_ratio)
                mutants.append(mutant)    

        return new_pop + mutants

    @staticmethod
    def run(base_path, last_pdts_path="",nb_base_products=100, dataset="cifar", training_epochs=25):

        if not os.path.isdir(base_path):
            os.mkdir(base_path)

        session_path = "{}/{}".format(base_path, dataset)

        if not os.path.isdir(session_path):
            os.mkdir(session_path)

        survival_rate = 0.1
        survival_count = max(5,math.ceil(survival_rate*nb_base_products))
        nb_product_perparent =  int((nb_base_products-survival_count) / survival_count)
        last_evolution_epoch = 0
        reset_keras()

        
        if os.path.isfile(last_pdts_path):
            print("Resuming training")
            f1 = open(last_pdts_path, 'r')
            last_population= pickle.load(f1)
            last_population = [KerasFeatureModel.parse_blocks(e) for e in last_population]

            pattern = 'products_e(\d+).pickled'
            result = re.findall(pattern, last_pdts_path) 
            if len(result):
                last_evolution_epoch = int(result[0])+1
                
        else:
            tensorflow_gen = TensorflowGenerator("lenet5",training_epochs, dataset)
            last_population = [tensorflow_gen.model]

        for evo in range(evolution_epochs):
            print("### evolution epoch {}".format(evo+last_evolution_epoch))

            new_pop = FullEvolution.select(last_population, survival_count)
            
            mutant_population = FullEvolution.evolve(evo, session_path, nb_product_perparent, dataset, new_pop , training_epochs )
            
            for index,model in enumerate(mutant_population):
                if model.accuracy==0:
                    #we do not train individuals preserved from previous generation
                    keras_model = TensorflowGenerator.build(model,dataset)
                    if not keras_model:
                        print("#### model is not valid ####")
                    else: 
                        TensorflowGenerator.train(model, training_epochs, TensorflowGenerator.default_batchsize, False,dataset)
                        TensorflowGenerator.eval_robustness(model)

                    pdt_path = "{}/{}products_e{}.json".format(
                        session_path, nb_base_products, evo)
                    
                    f1 = open(pdt_path, 'a')
                    vect = model.to_kerasvector().to_vector()
                    f1.write("\r\n{}:{}".format(index, json.dumps(vect)))
                    f1.close()

            last_population = [x for x in mutant_population if x.accuracy>0]
            pop = sorted(last_population,
                        key=lambda x: x.accuracy, reverse=True)
        
            pdt_path = "{}/{}products_e{}.pickled".format(
                session_path, nb_base_products, evo)
            print("### remaining total individuals {} saved to {}. top accuracy: {}".format(
                len(pop),pdt_path, pop[0].accuracy))
            f1 = open(pdt_path, 'w')
            #pickle.dump( [e.dump_blocks() for e in pop], f1)
            f1.close()

    

def main(argv):
    input_file = ''
    output_file = ''
    products_file = ''
    base = base_path
    nb_base_products=[20]
    dataset = "cifar"
    training_epochs = base_training_epochs
    
    try:
        opts, args = getopt.getopt(argv, "hn:d:b:p:t:", [
                                   "nb=","dataset=", "bpath=", "pfile=", "training_epoch="])
    except getopt.GetoptError:
        pass
    print("arguments {}".format(opts))
    for opt, arg in opts:
        
        if opt == '-h':
            print(
                'pledge_evolution.py -n <nb_architectures> -d <dataset> -b <base_path> -p <products_file> -t <training_epoch>')
            sys.exit()
        elif opt in ("-n", "--nb"):
            nb_base_products = arg.split("x")
        elif opt in ("-d", "--dataset"):
            dataset = arg
        elif opt in ("-b", "--bpath"):
            base = arg
        elif opt in ("-p", "--pfile"):
            products_file = arg
        elif opt in ("-t", "--training_epoch"):
            training_epochs = int(arg)

    FullEvolution.run(base, last_pdts_path=products_file, dataset=dataset, nb_base_products=int(nb_base_products[0]), training_epochs=training_epochs)

if __name__ == "__main__":
    main(sys.argv[1:])

