#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar  8 19:43:29 2020

@author: heavens
"""
import numpy as np
from sklearn.decomposition import PCA
from scipy.sparse import dok_matrix
import pickle
from sklearn import manifold
import os 

def tag2int(label):
    tags = list(set(label))
    int_label = [tags.index(x) for x in label]
    return np.asarray(int_label),tags

def one_hot_vector(label,class_n = None):
    label_n = len(label)
    if label.dtype != np.int:
        print("Input vector has a dtype %s"%(label.dtype))
        print("Transfering the data type into int.")
        _,tags = tag2int(label)
    else:
        tags = list(set(label))
    if class_n is None:
        class_n = len(tags)
    one_hot = np.zeros((label_n,class_n))
    for tag_idx,tag in enumerate(tags):
        one_hot[label==tag,tag_idx] = 1
    return one_hot,tags

def embedding_reduce(X,embedding):
    reduced_X = X@embedding
    return reduced_X,embedding

def tsne_reduce(X,dims = 2,method = "exact",tsne = None):
    if tsne is None:
        tsne = manifold.TSNE(n_components=dims, 
                             init='pca', 
                             random_state=0,
                             method = method)
    reduced_X = tsne.fit_transform(X)
    return reduced_X,tsne

def pca_reduce(X, dims=2,pca = None):
    """ Reduce the dimensions of X down to dims using PCA
    X has shape (n, d)
    Returns: The reduced X of shape (n, dims)
    		 The fitted PCA model used to reduce X
    """
    print("reducing dimensions using PCA")
    X = X - np.mean(X,axis = 0,keepdims = True)
    std = np.std(X,axis = 0, keepdims = True)
    std[std==0] += 1e-9 #Add a small pseudo count to avoid divide by 0 error.
    X = X/std
    if pca is None:
        pca = PCA(n_components = dims)
        pca.fit(X)
    X_reduced = pca.transform(X)
    return X_reduced,pca

def KL_divergence(prob1,prob2,pesudo=1e-6):
    if 0 in prob1:
        prob1 = prob1+pesudo
        prob1 = prob1/np.sum(prob1)
        print("Zero element in the first distribution, add pesudo count %.2f."%(pesudo))
    if 0 in prob2:
        prob2 = prob2+pesudo
        prob2 = prob2/np.sum(prob2)
        print("Zero element in the second distribution, add pesudo count %.2f."%(pesudo))
    kld = np.sum([x*np.log(x/y) for x,y in zip(prob1,prob2)])
    return kld

def get_adjacency(coordinate,
                  threshold_distance,
                  exclude_self = False):
    sample_n = coordinate.shape[0]
    adjacency = dok_matrix((sample_n,sample_n),bool)
    for i in np.arange(sample_n):
        difference = coordinate - coordinate[i]
        difference = difference**2
        euclidean_distance = np.sqrt(np.sum(difference,axis = 1))
        adjacency_array = euclidean_distance<threshold_distance
        if exclude_self:
            adjacency_array[i] = False
        cols = np.where(adjacency_array)[0]
        for col in cols:
            adjacency[i,col] = True
    return adjacency

def get_adjacency_knearest(coordinate,
                           nearest_k,
                           exclude_self = False):
    sample_n = coordinate.shape[0]
    adjacency = dok_matrix((sample_n,sample_n),bool)
    if exclude_self:
        nearest_k +=1
    for i in np.arange(sample_n):
        difference = coordinate - coordinate[i]
        euclidean_distance = np.sqrt(difference[:,0]**2+difference[:,1]**2)
        sort_idx = np.argsort(euclidean_distance)
        for col in sort_idx[:nearest_k]:
            adjacency[i,col] = True
        if exclude_self:
            adjacency[i,i] = False
    return adjacency

def get_knearest_distance(coordinate,
                          nearest_k,
                          exclude_self = False):
    sample_n = coordinate.shape[0]
    if exclude_self:
        nearest_k +=1
    distance_list = []
    for i in np.arange(sample_n):
        difference = coordinate - coordinate[i]
        euclidean_distance = np.sqrt(difference[:,0]**2+difference[:,1]**2)
        sort_distance = np.sort(euclidean_distance)
        distance_list.append(sort_distance[nearest_k])
    return distance_list    

def get_neighbourhood_count(adjacency, 
                            label,
                            exclude_self = True,
                            one_hot_label = True):
    """Get the neighbourhood type count given a adjacency matrix and label
    Args:
        adjacency: A N-by-N 0-1 adjacency matrix, N is the number of samples.
        label: A length N vector indicate the label tags.
        exclude_self: A boolean variable, if true the self-count is excluded.
    Return:
        nb_count: A N-by-M matrix given the neighbourhood count, where N is the
            number of sample, and M is the number of types of label.
    """
    sample_n = adjacency.shape[0]
    assert label.shape[0] == sample_n
    tags = np.unique(label)
    if one_hot_label:
        one_hot = label
    else:
        label_n = len(tags)
        one_hot = np.zeros((sample_n,label_n))
        one_hot[np.arange(sample_n),label] = 1
    if exclude_self:
        diag_mask = np.eye(sample_n).astype(bool)
        adjacency[diag_mask] = 0
    nb_count = adjacency.dot(one_hot)
    return nb_count

class DataLoader():
    def __init__(self,
                 xs,
                 y = None,
                 for_eval = False):
        """Base class for loading the data.
        Input Args:
            xs: The input data, can be a tuple of arrays with the same length in
                0 dimension.
            y: The label, need to have same length as x.
            for_eval: If the dataset is for evaluation.
        """
        if type(xs) is tuple:
            self.xs = xs
        else:
            self.xs = tuple(xs)
        self.y = y
        self.epochs_completed = 0
        self._index_in_epoch = 0
        self.sample_n = self.xs[0].shape[0]
        for x in self.xs:
            assert x.shape[0] == self.sample_n
        self._perm = np.arange(self.sample_n)
        self.for_eval = for_eval
        
    def read_into_memory(self, index):
        if self.for_eval:
            batch_y = None
        else:
            batch_y = self.y[index]
        batch_x = tuple([x[index] for x in self.xs])
        return batch_x,batch_y
    def _multi_concatenate(self,input_tuple,axis=0):
        result = [np.concatenate(x,axis = axis) for x in zip(*input_tuple)]
        return tuple(result)
    def next_batch(self, batch_size, shuffle=True):
        """Return next batch in batch_size from the data set.
            Input Args:
                batch_size:A scalar indicate the batch size.
                shuffle: boolean, indicate if the data should be shuffled after each epoch.
            Output Args:
                inputX,sequence_length,label_batch: tuple of (indx,vals,shape)
        """
        if self.epochs_completed>=1 and self.for_eval:
            print("Warning, evaluation dataset already finish one iteration.")
        start = self._index_in_epoch
        # Shuffle for the first epoch
        if self.epochs_completed == 0 and start == 0:
            if shuffle:
                np.random.shuffle(self._perm)
        # Go to the next epoch
        if start + batch_size >= self.sample_n:
            # Finished epoch
            self.epochs_completed += 1
            # Get the rest samples in this epoch
            rest_sample_n = self.sample_n - start
            x_rest_part, y_rest_part = self.read_into_memory(self._perm[start:self.sample_n])
            start = 0
            if self.for_eval:
                x_batch = x_rest_part
                y_batch = y_rest_part
                self._index_in_epoch = 0
                end = 0
            # Shuffle the data
            else:
                if shuffle:
                    np.random.shuffle(self._perm)
                # Start next epoch
                self._index_in_epoch = batch_size - rest_sample_n
                end = self._index_in_epoch
                x_new_part, y_new_part = self.read_into_memory(
                    self._perm[start:end])
                if x_rest_part[0].shape[0] == 0:
                    x_batch = x_new_part
                    y_batch = y_new_part
                elif x_new_part[0].shape[0] == 0:
                    x_batch = x_rest_part
                    y_batch = y_rest_part
                else:
                    x_batch = self._multi_concatenate((x_rest_part, x_new_part))
                    y_batch = np.concatenate((y_rest_part, y_new_part),axis = 0)
        else:
            self._index_in_epoch += batch_size
            end = self._index_in_epoch
            x_batch,y_batch = self.read_into_memory(
                self._perm[start:end])
        return x_batch,y_batch
    
def save_loader(loader,save_f):
    with open(save_f,'wb+') as f:
        pickle.dump(loader,f)

def save_smfish(loader,save_prefix,is_labeled=False):
    """Save the data in the loader as the smfishHmrf format:
    http://spatial.rc.fas.harvard.edu/install.html
    """
    norm_expr = loader.gene_expression - np.mean(loader.gene_expression,axis = 1,keepdims = True)
    std_expr = np.std(loader.gene_expression,axis = 1,keepdims = True)
    zero_mask = std_expr != 0
    zero_mask = np.reshape(zero_mask,newshape=zero_mask.shape[0])
    norm_expr = norm_expr[zero_mask,:] / std_expr[zero_mask]
    with open(save_prefix+'.expression','w+') as f:
        for i,expr in enumerate(norm_expr):
            f.write("%d %s\n"%(i+1,' '.join([str(e) for e in expr])))
    coordinate = loader.coordinate[zero_mask,:]
    with open(save_prefix+'.coordinates','w+') as f:
        if coordinate.shape[1]==2:
            for i,p in enumerate(coordinate):
                f.write("%d %.3f %.3f %.3f\n"%(i+1,0,p[0],p[1]))
        elif coordinate.shape[1] ==3:
            for i,p in enumerate(coordinate):
                f.write("%d %.3f %.3f %.3f\n"%(i+1,p[2],p[0],p[1]))
    with open(save_prefix+'.genes','w+') as f:
        for i,g in enumerate(loader.gene_list):
            f.write("%s\n"%(g))
    if is_labeled:
        with open(save_prefix+'.labels','w+') as f:
            for i,c in enumerate(loader.cell_labels):
                f.write("%d %d\n"%(i+1,c))


def load_loader(save_f):
    with open(save_f,'rb') as f:
        loader = pickle.load(f)
    return loader