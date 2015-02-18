"""
DESCRIPTORS.TEXTURE: textural descriptors from grey-scale and binary images.
@author: vlad
"""
from __future__ import (absolute_import, division, print_function, unicode_literals)

__version__ = 0.3
__author__ = 'Vlad Popovici'


from abc import ABCMeta, abstractmethod

import numpy as np
from numpy import dot

from scipy import ndimage as nd
from scipy.linalg import norm
from scipy.stats import entropy
from scipy.signal import convolve2d

from skimage.exposure import rescale_intensity
from skimage.filter import gabor_kernel
from skimage.filter.rank import median
from skimage.feature.texture import greycoprops, greycomatrix, local_binary_pattern
from skimage.feature import hog
from skimage.morphology import disk
from skimage.util import img_as_float

from .basic import *


class GaborDescriptor(LocalDescriptor):
    """
    Computes Gabor descriptors from an image. These descriptors are the means
    and variances of the filter responses obtained by convolving an image with
    a bank of Gabor filters.
    """
    def __init__(self, theta=np.array([0.0, np.pi/4.0, np.pi/2.0, 3.0*np.pi/4.0],
                                      dtype=np.double),
                 freq=np.array([3.0/4.0, 3.0/8.0, 3.0/16.0], dtype=np.double),
                 sigma=np.array([1.0, 2*np.sqrt(2.0)], dtype=np.double),
                 normalized=True):
        """
        Initialize the Gabor kernels (only real part).

        Args:
            theta: numpy.ndarray (vector)
            Contains the orientations of the filter; defaults to [0, pi/4, pi/2, 3*pi/4].

            freq: numpy.ndarray (vector)
            The frequencies of the Gabor filter; defaults to [3/4, 3/8, 3/16].

            sigma: numpy.ndarray (vector)
            The sigma parameter for the Gaussian smoothing filter; defaults to [1, 2*sqrt(2)].

            normalized: bool
            If true, the kernels are normalized
        """

        self.kernels_ = [np.real(gabor_kernel(frequency=f, theta=t, sigma_x=s,
                                              sigma_y=s))
                         for f in freq for s in sigma for t in theta]
        if normalized:
            for k, krn in enumerate(self.kernels_):
                self.kernels_[k] = krn / np.sqrt((krn**2).sum())

        return

    def compute(self, image):
        """
        Compute the Gabor descriptors on the given image.

        Args:
            image: numpy.ndarray (.ndim=2)
            Grey scale image.

        Returns:
            numpy.ndarray (vector) containing the Gabor descriptors (means followed
            by the variances of the filter responses)
        """
        try:
            image = img_as_float(image)
            nk = len(self.kernels_)
            ft = np.zeros(2*nk, dtype=np.double)
            for k, krn in enumerate(self.kernels_):
                flt = nd.convolve(image, krn, mode='wrap')
                ft[k] = flt.mean()
                ft[k+nk] = flt.var()
        except:
            print("Error in GaborDescriptor.compute()")


        return ft

    @staticmethod
    def dist(ft1, ft2, method='Euclidean'):
        """
        Compute the distance between two sets of Gabor features. Possible distance types
        are:
            -Euclidean
            -cosine distance: this is not a proper distance!

        """
        dm = {'euclidean' : lambda x_, y_: norm(x_-y_),
              'cosine': lambda x_, y_: dot(x_, y_) / (norm(x_)*norm(y_))
              }
        method = method.lower()
        if method not in dm.keys():
            raise ValueError('Unknown method')

        return dm[method](ft1, ft2)
## end class GaborDescriptors


class GLCMDescriptor(LocalDescriptor):
    """
    Grey Level Co-occurrence Matrix: the image is decomposed into a number of
    non-overlapping regions, and the GLCM features are computed on each of these
    regions.
    """
    def __init__(self, wsize, dist=0.0, theta=0.0, levels=256, which=['dissimilarity', 'correlation'],
                 symmetric=True, normed=True):
        """
        Initialize GLCM.

        Args:
            wsize: uint
            window size: the image is decomposed into small non-overlapping regions of size
            <wsize x wsize> from which the GLCMs are computed. If the last region in a row or
            the last row in an image are smaller than the required size, then they are not
            used in computing the features.

            dist: uint
            pair distance

            theta: float
            pair angle

            levels: uint
            number of grey levels

            which: string
            which features to be computed from the GLCM. See the help for
            skimage.feature.texture.greycoprops for details

            symmetric: bool
            consider symmetric pairs?

            normed: bool
            normalize the co-occurrence matrix, before computing the features?
        """
        self.wsize_ = wsize
        self.dist_ = dist
        self.theta_ = theta
        self.levels_ = levels
        self.which_feats_ = [w.lower() for w in which]
        self.symmetric_ = symmetric
        self.normed_ = normed

        return


    def compute(self, image):
        """
        Compute the GLCM features.
        """

        assert(image.ndim == 2)
        w, h = image.shape

        nw = int(w / self.wsize_)
        nh = int(h / self.wsize_)

        nf = len(self.which_feats_)

        ft = np.zeros((nf, nw*nh))  # features will be on rows
        k = 0
        for x in np.arange(0, nw):
            for y in np.arange(0, nh):
                x0, y0 = x * self.wsize_, y * self.wsize_
                x1, y1 = x0 + self.wsize_, y0 + self.wsize_

                glcm = greycomatrix(image[y0:y1, x0:x1],
                                    self.dist_, self.theta_, self.levels_,
                                    self.symmetric_, self.normed_)
                ft[:,k] = np.array([greycoprops(glcm, f)[0,0] for f in self.which_feats_])
                k += 1

        res = {}
        k = 0
        for f in self.which_feats_:
            res[f] = ft[k,:]
            k += 1

        return res


    @staticmethod
    def dist(ft1, ft2, method='bh'):
        """
        Computes the distance between two sets of GLCM features. The features are
        assumed to have been computed using the same parameters. The distance is
        based on comparing the distributions of these features.

        Args:
            ft1, ft2: dict
            each dictionary contains for each feature a vector of values computed
            from the images

            method: string
            the method used for computing the distance between the histograms of features:
            'kl' - Kullback-Leibler divergence (symmetrized by 0.5*(KL(p,q)+KL(q,p))
            'js' - Jensen-Shannon divergence: 0.5*(KL(p,m)+KL(q,m)) where m=(p+q)/2
            'bh' - Bhattacharyya distance: -log(sqrt(sum_i (p_i*q_i)))
            'ma' - Matusita distance: sqrt(sum_i (sqrt(p_i)-sqrt(q_i))**2)

        Returns:
            dict
            a dictionary with distances computed between pairs of features
        """
        # distance methods
        dm = {'kl': lambda x_, y_: 0.5*(entropy(x_, y_) + entropy(y_, x_)),
              'js': lambda x_, y_: 0.5*(entropy(x_, 0.5*(x_+y_))+entropy(y_,0.5*(x_+y_))),
              'bh': lambda x_, y_: -np.log(np.sum(np.sqrt(x_*y_))),
              'ma': lambda x_, y_: np.sqrt(np.sum((np.sqrt(x_)-np.sqrt(y_))**2))
              }


        method = method.lower()
        if method not in dm.keys():
            raise ValueError('Unknown method')

        res = {}
        for k in ft1.keys():
            if k in ft2.keys():
                # build the histograms:
                mn = min(ft1[k].min(), ft2[k].min())
                mx = max(ft1[k].max(), ft2[k].max())
                h1,_ = np.histogram(ft1[k], normed=True, bins=10, range=(mn,mx))
                h2,_ = np.histogram(ft2[k], normed=True, bins=10, range=(mn,mx))
                res[k] = dm[method](h1, h2)

        return res
## end class GLCMDescriptors


class LBPDescriptor(LocalDescriptor):
    """
    Local Binary Pattern for texture description. A LBP descriptor set is a
    histogram of LBPs computed from the image.
    """
    def __init__(self, radius=3, npoints=None, method='uniform'):
        """
        Initialize a LBP descriptor set. See skimage.feature.texture.local_binary_pattern
        for details on the meaning of parameters.

        Args:
            radius: int
            defaults to 3

            npoints: int
            defaults to None. If None, npoints is set to 8*radius

            method: string
            defaults to 'uniform'
        """

        self.radius_ = radius
        self.npoints_ = radius*8 if npoints is None else npoints
        self.method_ = method.lower()
        self.nhbins_ = self.npoints_ + 2

        return

    def compute(self, image):
        """
        Compute the LBP features. These features are returned as histograms of
        LBPs.
        """
        try:
            lbp = local_binary_pattern(image, self.npoints_, self.radius_, self.method_)
            hist, _ = np.histogram(lbp, normed=True, bins=self.nhbins_, range=(0, self.nhbins_))
        except:
            print("Error in LBPDescriptor.compute()")

        return hist


    @staticmethod
    def dist(ft1, ft2, method='bh'):
        """
        Computes the distance between two sets of LBP features. The features are
        assumed to have been computed using the same parameters. The features
        are represented as histograms of LBPs.

        Args:
            ft1, ft2: numpy.ndarray (vector)
            histograms of LBPs as returned by compute()

            method: string
            the method used for computing the distance between the two sets of features:
            'kl' - Kullback-Leibler divergence (symmetrized by 0.5*(KL(p,q)+KL(q,p))
            'js' - Jensen-Shannon divergence: 0.5*(KL(p,m)+KL(q,m)) where m=(p+q)/2
            'bh' - Bhattacharyya distance: -log(sqrt(sum_i (p_i*q_i)))
            'ma' - Matusita distance: sqrt(sum_i (sqrt(p_i)-sqrt(q_i))**2)
        """
        # distance methods
        dm = {'kl': lambda x_, y_: 0.5*(entropy(x_, y_) + entropy(y_, x_)),
              'js': lambda x_, y_: 0.5*(entropy(x_, 0.5*(x_+y_))+entropy(y_,0.5*(x_+y_))),
              'bh': lambda x_, y_: -np.log(np.sum(np.sqrt(x_*y_))),
              'ma': lambda x_, y_: np.sqrt(np.sum((np.sqrt(x_)-np.sqrt(y_))**2))
              }


        method = method.lower()
        if method not in dm.keys():
            raise ValueError('Unknown method')

        return dm[method](ft1, ft2)
## end class LBPDescriptors


# MFSDescriptors - Multi-Fractal Dimensions
class MFSDescriptor(LocalDescriptor):
    """
    Multi-Fractal Dimensions for texture description.

    Adapted from IMFRACTAL project at https://github.com/rbaravalle/imfractal

    """
    def __init__(self, _nlevels_avg=1, _wsize=15, _niter=1):
        """
        Initialize an MFDDescriptors object.

        Arguments:
            _nlevels_avg: number of levels to be averaged in density computation (uint)
               =1: no averaging
            _wsize: size of the window for computing descriptors (uint)
            _niter: number of iterations
        """
        self.nlevels_avg = _nlevels_avg
        self.wsize = _wsize
        self.niter = _niter

        return

    def compute(self, im):
        """
        Computes MFS over the given image.

        Arguments:
            im: image (grey-scale) (numpy.ndarray)

        Returns:
            a vector of descriptors (numpy.array)
        """
        ## TODO: this needs much polishing to get it run faster!

        assert(im.ndim == 2)
        #Using [0..255] to denote the intensity profile of the image
        grayscale_box =[0, 255]

        #Preprocessing: default intensity value of image ranges from 0 to 255
        if abs(im).max() < 1:
            im = rescale_intensity(im, out_range=(0, 255))

        #######################

        ### Estimating density function of the image
        ### by solving least squares for D in  the equation
        ### log10(bw) = D*log10(c) + b
        r = 1.0/max(im.shape)
        c = np.log10(r * np.arange(start=1, stop=self.nlevels_avg+1))

        bw = np.zeros((self.nlevels_avg, im.shape[0], im.shape[1]), dtype=np.float32)
        bw[0,:,:] = im + 1

        def _gauss_krn(size):
            """ Returns a normalized 2D gauss kernel array for convolutions """
            if size <= 3:
                sigma = 1.5
            else:
                sigma = size / 2.0

            y, x = np.mgrid[-(size-1.0)/2.0:(size-1.0)/2.0+1, -(size-1.0)/2.0:(size-1.0)/2.0+1]
            s2 = 2.0 * sigma**2
            g = np.exp(-(x**2 + y**2) / s2)

            return g / g.sum()

        k = 1
        if self.nlevels_avg > 1:
            bw[1,:,:] = convolve2d(bw[0,:,:], _gauss_krn(k+1), mode="full")[1:,1:]*((k+1)**2)

        for k in np.arange(2, self.nlevels_avg):
            temp = convolve2d(bw[0,:,:], _gauss_krn(k+1), mode="full")*((k+1)**2)
            if k == 4:
                bw[k] = temp[k-1-1:temp.shape[0]-(k/2),k-1-1:temp.shape[1]-(k/2)]
            else:
                bw[k] = temp[k-1:temp.shape[0]-(1),k-1:temp.shape[1]-(1)]

        bw = np.log10(bw)
        n1 = np.sum(c**2)
        n2 = bw[0]*c[0]
        for k in np.arange(1, self.nlevels_avg):
            n2 += bw[k] * c[k]

        sum3 = np.sum(bw, axis=0)

        if self.nlevels_avg > 1:
            D = (n2*self.nlevels_avg - c.sum()*sum3) / (n1*self.nlevels_avg - c.sum()**2)
            min_D, max_D  = 1.0, 4.0
            D = grayscale_box[1] * (D-min_D)/(max_D - min_D) + grayscale_box[0]
        else:
            D = im

        D = D[self.nlevels_avg-1:D.shape[0]-self.nlevels_avg+1, self.nlevels_avg-1:D.shape[1]-self.nlevels_avg+1]

        IM = np.zeros(D.shape)
        gap = np.ceil((grayscale_box[1] - grayscale_box[0])/np.float32(self.wsize))
        center = np.zeros(self.wsize)
        for k in np.arange(1, self.wsize+1):
            bin_min = (k-1) * gap
            bin_max = k * gap - 1
            center[k-1] = round((bin_min + bin_max) / 2.0)
            D = ((D <= bin_max) & (D >= bin_min)).choose(D, center[k-1])

        D = ((D >= bin_max)).choose(D,0)
        D = ((D < 0)).choose(D,0)
        IM = D

        #Constructing the filter for approximating log fitting
        r = max(IM.shape)
        c = np.zeros(self.niter)
        c[0] = 1;
        for k in range(1,self.niter):
            c[k] = c[k-1]/(k+1)
        c = c / sum(c);

        #Construct level sets
        Idx_IM = np.zeros(IM.shape);
        for k in range(0,self.wsize):
            IM = (IM == center[k]).choose(IM,k+1)

        Idx_IM = IM
        IM = np.zeros(IM.shape)

        #Estimate MFS by box-counting
        num = np.zeros(self.niter)
        MFS = np.zeros(self.wsize)
        for k in range(1,self.wsize+1):
            IM = np.zeros(IM.shape)
            IM = (Idx_IM==k).choose(Idx_IM,255+k)
            IM = (IM<255+k).choose(IM,0)
            IM = (IM>0).choose(IM,1)
            temp = max(IM.sum(),1)
            num[0] = np.log10(temp)/np.log10(r);
            for j in range(2,self.niter+1):
                mask = np.ones((j,j))
                bw = convolve2d(IM, mask,mode="full")[1:,1:]
                indx = np.arange(0,IM.shape[0],j)
                indy = np.arange(0,IM.shape[1],j)
                bw = bw[np.ix_(indx,indy)]
                idx = (bw>0).sum()
                temp = max(idx,1)
                num[j-1] = np.log10(temp)/np.log10(r/j)

            MFS[k-1] = sum(c*num)

        return MFS

    @staticmethod
    def dist(ft1, ft2, method='euclidean'):
        """
        Compute the distance between two sets of multifractal dimension features.
        Possible distance types are:
            -Euclidean
            -cosine distance: this is not a proper distance!

        """
        assert (ft1.ndim == ft2.ndim == 1)
        assert (ft1.size == ft2.size)


        dm = {'euclidean' : lambda x_, y_: norm(x_-y_),
              'cosine': lambda x_, y_: dot(x_, y_) / (norm(x_)*norm(y_))
              }
        method = method.lower()
        if method not in dm.keys():
            raise ValueError('Unknown method')

        return dm[method](ft1, ft2)
# end class MFSDescriptors


class HOGDescriptor(LocalDescriptor):
    """
    Provides local descriptors in terms of histograms of oriented gradients.
    """
    def __init__(self, _norient=9, _ppc=(128,128), _cpb=(4,4)):
        """
        Initialize an HOGDescriptors object. For details see the HOG
        descriptor in sciki-image package:
        skimage.feature.hog

        :param _norient: uint
          number of orientations of the gradients
        :param _ppc: uint
          pixels per cell
        :param _cpb: uint
          cells per block
        """
        self.norient = _norient
        self.ppc = _ppc
        self.cpb = _cpb

        return


    def compute(self, image):
        """
        Computes HOG on a given image.

        :param image: numpy.ndarray

        :return: numpy.ndarray
          a vector of features
        """
        r = hog(image, pixels_per_cell=self.ppc, cells_per_block=self.cpb,
                visualise=False, normalise=False)

        return r


    @staticmethod
    def dist(ft1, ft2, method=None):
        """
        Compute the distance between two sets of HOG features. Possible distance types
        are:
            -Euclidean
            -cosine distance: this is not a proper distance!

        """
        dm = {'euclidean' : lambda x_, y_: norm(x_-y_),
              'cosine': lambda x_, y_: dot(x_, y_) / (norm(x_)*norm(y_))
              }

        method = method.lower()
        if method not in dm.keys():
            raise ValueError('Unknown method')

        return dm[method](ft1, ft2)
# end HOGDescriptors


class HistDescriptor(LocalDescriptor):
    """
    Provides local descriptors in terms of histograms of grey levels.
    """
    def __init__(self, _interval=(0,1), _nbins=10):
        """
        Initialize an HistDescriptors object: a simple histogram of
        grey-levels

        :param _interval: tuple
          the minimum and maximum values to be accounted for
        :param _nbins: uint
          number of bins in the histogram
        """
        self.interval = _interval
        self.nbins = _nbins

        return


    def compute(self, image):
        """
        Computes the histogram on a given image.

        :param image: numpy.ndarray

        :return: numpy.ndarray
          a vector of frequencies
        """
        if image.ndim != 2:
            raise ValueError("Only grey-level images are supported")

        h,_ = np.histogram(image, normed=True, bins=self.nbins, range=self.interval)

        return h


    @staticmethod
    def dist(ft1, ft2, method='bh'):
        """
        Computes the distance between two sets of histogram features.

        Args:
            ft1, ft2: numpy.ndarray (vector)
            histograms as returned by compute()

            method: string
            the method used for computing the distance between the two sets of features:
            'kl' - Kullback-Leibler divergence (symmetrized by 0.5*(KL(p,q)+KL(q,p))
            'js' - Jensen-Shannon divergence: 0.5*(KL(p,m)+KL(q,m)) where m=(p+q)/2
            'bh' - Bhattacharyya distance: -log(sqrt(sum_i (p_i*q_i)))
            'ma' - Matusita distance: sqrt(sum_i (sqrt(p_i)-sqrt(q_i))**2)
        """
        # distance methods
        dm = {'kl': lambda x_, y_: 0.5*(entropy(x_, y_) + entropy(y_, x_)),
              'js': lambda x_, y_: 0.5*(entropy(x_, 0.5*(x_+y_))+entropy(y_,0.5*(x_+y_))),
              'bh': lambda x_, y_: -np.log(np.sum(np.sqrt(x_*y_))),
              'ma': lambda x_, y_: np.sqrt(np.sum((np.sqrt(x_)-np.sqrt(y_))**2))
              }


        method = method.lower()
        if method not in dm.keys():
            raise ValueError('Unknown method')

        return dm[method](ft1, ft2)
# end HistDescriptors


##
## Texture from binary images
##



def compactness(_img):

    ## Lookup table for the empirical distribution of median(img)/img
    ## in the case of a random image (white noise), for varying
    ## proportions of white pixels in the image (0.1, 0.2, ..., 1.0).
    ## The distributions are approximated by Gaussians, and the
    ## corresponding means and standard deviations are stored.

    prop = np.linspace(0.1, 1.0, 10)
    emp_distrib_mean = np.array([4.4216484763437432e-06, 0.0011018116582350559,
                                 0.042247116747488218, 0.34893587605251208,
                                 1.0046008733628913, 1.4397675817057451,
                                 1.4115741958770296, 1.2497935146232551,
                                 1.1111058415275834, 1.0])
    emp_distrib_std = np.array([2.7360459073474441e-05, 0.00051125394394966434,
                                0.0038856377648490894, 0.012029872915543046,
                                0.013957075037020938, 0.0057246251730834283,
                                0.0028750796874699143, 0.0023709207886137384,
                                0.0015018959493632007, 0.0])
    if _img.ndim != 2:
        raise ValueError('The input image must be a 2D binary image.')

    _img = (_img != 0).astype(np.uint8)
    _med = median(_img, disk(3))

    # "proportion of white pixels" in the image:
    swp = np.sum(_img, dtype=np.float64)
    pwp = swp / _img.size

    # compactness coefficient
    cf = np.sum(_med, dtype=np.float64) / swp

    # standardize using the "closest" Gaussian from the list of empirical
    # distributions:
    k = np.argmin(np.abs(prop - pwp))

    # this should make the coeff more or less normally distributed N(0,1)
    cf = (cf - emp_distrib_mean[k]) / emp_distrib_std[k]

    return cf