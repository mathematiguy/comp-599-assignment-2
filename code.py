import csv
import json
import itertools
import random
from typing import Union, Callable

import numpy as np
from sklearn.decomposition import PCA
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader
from tqdm.auto import tqdm


# ########################## PART 1: PROVIDED CODE ##############################
def load_datasets(data_directory: str) -> "Union[dict, dict]":
    """
    Reads the training and validation splits from disk and load
    them into memory.

    Parameters
    ----------
    data_directory: str
        The directory where the data is stored.

    Returns
    -------
    train: dict
        The train dictionary with keys 'premise', 'hypothesis', 'label'.
    validation: dict
        The validation dictionary with keys 'premise', 'hypothesis', 'label'.
    """
    import json
    import os

    with open(os.path.join(data_directory, "train.json"), "r") as f:
        train = json.load(f)

    with open(os.path.join(data_directory, "validation.json"), "r") as f:
        valid = json.load(f)

    return train, valid


def tokenize_w2v(
    text: "list[str]", max_length: int = None, normalize: bool = True
) -> "list[list[str]]":
    """
    Tokenize the text into individual words (nested list of string),
    where the inner list represent a single example.

    Parameters
    ----------
    text: list of strings
        Your cleaned text data (either premise or hypothesis).
    max_length: int, optional
        The maximum length of the sequence. If None, it will be
        the maximum length of the dataset.
    normalize: bool, default True
        Whether to normalize the text before tokenizing (i.e. lower
        case, remove punctuations)
    Returns
    -------
    list of list of strings
        The same text data, but tokenized by space.

    Examples
    --------
    >>> tokenize(['Hello, world!', 'This is a test.'], normalize=True)
    [['hello', 'world'], ['this', 'is', 'a', 'test']]
    """
    import re

    if normalize:
        regexp = re.compile("[^a-zA-Z ]+")
        # Lowercase, Remove non-alphanum
        text = [regexp.sub("", t.lower()) for t in text]

    return [t.split()[:max_length] for t in text]


def build_word_counts(token_list: "list[list[str]]") -> "dict[str, int]":
    """
    This builds a dictionary that keeps track of how often each word appears
    in the dataset.

    Parameters
    ----------
    token_list: list of list of strings
        The list of tokens obtained from tokenize().

    Returns
    -------
    dict of {str: int}
        A dictionary mapping every word to an integer representing the
        appearance frequency.

    Notes
    -----
    If you have  multiple lists, you should concatenate them before using
    this function, e.g. generate_mapping(list1 + list2 + list3)
    """
    word_counts = {}

    for words in token_list:
        for word in words:
            word_counts[word] = word_counts.get(word, 0) + 1

    return word_counts


def build_index_map(
    word_counts: "dict[str, int]", max_words: int = None
) -> "dict[str, int]":
    """
    Builds an index map that converts a word into an integer that can be
    accepted by our model.

    Parameters
    ----------
    word_counts: dict of {str: int}
        A dictionary mapping every word to an integer representing the
        appearance frequency.
    max_words: int, optional
        The maximum number of words to be included in the index map. By
        default, it is None, which means all words are taken into account.

    Returns
    -------
    dict of {str: int}
        A dictionary mapping every word to an integer representing the
        index in the embedding.
    """

    sorted_counts = sorted(word_counts.items(), key=lambda item: item[1], reverse=True)
    if max_words:
        sorted_counts = sorted_counts[: max_words - 1]

    sorted_words = ["[PAD]"] + [item[0] for item in sorted_counts]

    return {word: ix for ix, word in enumerate(sorted_words)}


def tokens_to_ix(
    tokens: "list[list[str]]", index_map: "dict[str, int]"
) -> "list[list[int]]":
    """
    Converts a nested list of tokens to a nested list of indices using
    the index map.

    Parameters
    ----------
    tokens: list of list of strings
        The list of tokens obtained from tokenize().
    index_map: dict of {str: int}
        The index map from build_index_map().

    Returns
    -------
    list of list of int
        The same tokens, but converted into indices.

    Notes
    -----
    Words that have not been seen are ignored.
    """
    return [
        [index_map[word] for word in words if word in index_map] for words in tokens
    ]


def collate_cbow(batch):
    """
    Collate function for the CBOW model. This is needed only for CBOW but not skip-gram, since
    skip-gram indices can be directly formatted by DataLoader. For more information, look at the
    usage at the end of this file.
    """
    sources = []
    targets = []

    for s, t in batch:
        sources.append(s)
        targets.append(t)

    sources = torch.tensor(sources, dtype=torch.int64)
    targets = torch.tensor(targets, dtype=torch.int64)

    return sources, targets


def train_w2v(model, optimizer, loader, device):
    """
    Code to train the model. See usage at the end.
    """
    model.train()

    for x, y in tqdm(loader, miniters=20, leave=False):
        x, y = x.to(device), y.to(device)
        optimizer.zero_grad()

        y_pred = model(x)

        loss = F.cross_entropy(y_pred, y)
        loss.backward()

        optimizer.step()

    return loss


class Word2VecDataset(torch.utils.data.Dataset):
    """
    Dataset is needed in order to use the DataLoader. See usage at the end.
    """

    def __init__(self, sources, targets):
        self.sources = sources
        self.targets = targets
        assert len(self.sources) == len(self.targets)

    def __len__(self):
        return len(self.sources)

    def __getitem__(self, idx):
        return self.sources[idx], self.targets[idx]


# ########################## PART 2: PROVIDED CODE ##############################
def load_glove_embeddings(file_path: str) -> "dict[str, np.ndarray]":
    """
    Loads trained GloVe embeddings downloaded from:
        https://nlp.stanford.edu/projects/glove/
    """
    word_to_embedding = {}
    with open(file_path, "r") as f:
        for line in f:
            word, raw_embeddings = line.split()[0], line.split()[1:]
            embedding = np.array(raw_embeddings, dtype=np.float64)
            word_to_embedding[word] = embedding
    return word_to_embedding


def load_professions(file_path: str) -> "list[str]":
    """
    Loads profession words from the BEC-Pro dataset. For more information on BEC-Pro,
    see:
        https://arxiv.org/abs/2010.14534
    """
    with open(file_path, "r") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)  # Skip the header.
        professions = [row[1] for row in reader]
    return professions


def load_gender_attribute_words(file_path: str) -> "list[list[str]]":
    """
    Loads the gender attribute words from: https://aclanthology.org/N18-2003/
    """
    with open(file_path, "r") as f:
        gender_attribute_words = json.load(f)
    return gender_attribute_words


def compute_partitions(XY: "list[str]") -> "list[tuple]":
    """
    Computes all of the possible partitions of X union Y into equal sized sets.

    Parameters
    ----------
    XY: list of strings
        The list of all target words.

    Returns
    -------
    list of tuples of strings
        List containing all of the possible partitions of X union Y into equal sized
        sets.
    """
    return list(itertools.combinations(XY, len(XY) // 2))


def p_value_permutation_test(
    X: "list[str]",
    Y: "list[str]",
    A: "list[str]",
    B: "list[str]",
    word_to_embedding: "dict[str, np.array]",
) -> float:
    """
    Computes the p-value for a permutation test on the WEAT test statistic.

    Parameters
    ----------
    X: list of strings
        List of target words.
    Y: list of strings
        List of target words.
    A: list of strings
        List of attribute words.
    B: list of strings
        List of attribute words.
    word_to_embedding: dict of {str: np.array}
        Dict containing the loaded GloVe embeddings. The dict maps from words
        (e.g., 'the') to corresponding embeddings.

    Returns
    -------
    float
        The computed p-value for the permutation test.
    """
    # Compute the actual test statistic.
    s = weat_differential_association(X, Y, A, B, word_to_embedding, weat_association)

    XY = X + Y
    partitions = compute_partitions(XY)

    total = 0
    total_true = 0
    for X_i in partitions:
        # Compute the complement set.
        Y_i = [w for w in XY if w not in X_i]

        s_i = weat_differential_association(
            X_i, Y_i, A, B, word_to_embedding, weat_association
        )

        if s_i > s:
            total_true += 1
        total += 1

    p = total_true / total

    return p


# ######################## PART 1: YOUR WORK STARTS HERE ########################


def build_current_surrounding_pairs(indices: "list[int]", window_size: int = 2):
    """
    Given a list of indices, this produces the following:
        - surrounding_indices: a list of context windows for each index
        - current_indices: the centre of each context window

    Each context window has constant width of 2 * window_size.
    Windows at the beginning or end are dropped to ensure this is the case.
    """
    # Drop start + end tokens
    current_indices = indices[window_size:-window_size]

    surrounding_indices = [
        indices[i - window_size : i] + indices[i + 1 : i + window_size + 1]
        for i, cur in enumerate(indices)
    ][window_size:-window_size]

    return surrounding_indices, current_indices


def expand_surrounding_words(
    ix_surroundings: "list[list[int]]", ix_current: "list[int]"
):

    if len(ix_surroundings) == 0:
        return [], []
    else:
        window_size = len(ix_surroundings[0])

    flatten_list = lambda l: [x for y in l for x in y]

    ix_surroundings_expanded = flatten_list(ix_surroundings)
    ix_current_expanded = flatten_list([[x] * window_size for x in ix_current])

    return ix_surroundings_expanded, ix_current_expanded


def cbow_preprocessing(indices_list: "list[list[int]]", window_size: int = 2):

    sources = []
    targets = []
    for indices in indices_list:
        surrounding, current = build_current_surrounding_pairs(indices, window_size)
        sources += surrounding
        targets += current

    return sources, targets


def skipgram_preprocessing(indices_list: "list[list[int]]", window_size: int = 2):
    sources = []
    targets = []
    for indices in indices_list:
        surrounding, current = build_current_surrounding_pairs(indices, window_size)
        surroundings_expanded, current_expanded = expand_surrounding_words(
            surrounding, current
        )
        sources += surroundings_expanded
        targets += current_expanded

    return sources, targets


class SharedNNLM:
    def __init__(self, num_words: int, embed_dim: int):
        """
        SkipGram and CBOW actually use the same underlying architecture,
        which is a simplification of the NNLM model (no hidden layer)
        and the input and output layers share the same weights. You will
        need to implement this here.

        Notes
        -----
          - This is not a nn.Module, it's an intermediate class used
            solely in the SkipGram and CBOW modules later.
          - Projection does not have a bias in word2vec
        """

        self.embedding = nn.Embedding(num_words, embed_dim)
        self.projection = nn.Linear(embed_dim, num_words, bias=False)

        self.bind_weights()

    def bind_weights(self):
        """
        Bind the weights of the embedding layer with the projection layer.
        This mean they are the same object (and are updated together when
        you do the backward pass).
        """
        emb = self.get_emb()
        proj = self.get_proj()

        proj.weight = emb.weight

    def get_emb(self):
        return self.embedding

    def get_proj(self):
        return self.projection


class SkipGram(nn.Module):
    """
    Use SharedNNLM to implement skip-gram. Only the forward() method differs from CBOW.
    """

    def __init__(self, num_words: int, embed_dim: int = 100):
        """
        Parameters
        ----------
        num_words: int
            The number of words in the vocabulary.
        embed_dim: int
            The dimension of the word embeddings.
        """
        super().__init__()

        self.nnlm = SharedNNLM(num_words, embed_dim)
        self.emb = self.nnlm.get_emb()
        self.proj = self.nnlm.get_proj()

    def forward(self, x: torch.Tensor):
        emb_x = self.emb(x)
        proj_x = self.proj(emb_x)
        return proj_x


class CBOW(nn.Module):
    """
    Use SharedNNLM to implement CBOW. Only the forward() method differs from SkipGram,
    as you have to sum up the embedding of all the surrounding words (see paper for details).
    """

    def __init__(self, num_words: int, embed_dim: int = 100):
        """
        Parameters
        ----------
        num_words: int
            The number of words in the vocabulary.
        embed_dim: int
            The dimension of the word embeddings.
        """
        super().__init__()

        self.nnlm = SharedNNLM(num_words, embed_dim)
        self.emb = self.nnlm.get_emb()
        self.proj = self.nnlm.get_proj()

    def forward(self, x: torch.Tensor):
        emb_x = self.emb(x).sum(axis=1)
        proj_x = self.proj(emb_x)
        return proj_x


def compute_topk_similar(
    word_emb: torch.Tensor, w2v_emb_weight: torch.Tensor, k
) -> list:

    # Normalize word embedding + embedding tensor
    word_emb_normalized = F.normalize(word_emb.flatten(), dim=0)
    w2v_emb_weight_normalized = F.normalize(w2v_emb_weight, dim=1)

    # Calculate similarity matrix
    similarity = torch.matmul(w2v_emb_weight_normalized, word_emb_normalized)

    # Get top k most similar
    top_k = torch.topk(similarity, k + 1)

    # Skip the first entry, which will be the original vector
    return top_k.indices[1:].tolist()


@torch.no_grad()
def retrieve_similar_words(
    model: nn.Module,
    word: str,
    index_map: "dict[str, int]",
    index_to_word: "dict[int, str]",
    k: int = 5,
) -> "list[str]":

    word_index = index_map[word]
    w2v_emb_weight = model.emb.weight
    word_emb = w2v_emb_weight[word_index, :]

    top_k = compute_topk_similar(word_emb, w2v_emb_weight, k)
    results = [index_to_word[idx] for idx in top_k]

    return results


@torch.no_grad()
def word_analogy(
    model: nn.Module,
    word_a: str,
    word_b: str,
    word_c: str,
    index_map: "dict[str, int]",
    index_to_word: "dict[int, str]",
    k: int = 5,
) -> "list[str]":

    w2v_emb_weight = model.emb.weight

    word_a_index = index_map[word_a]
    word_b_index = index_map[word_b]
    word_c_index = index_map[word_c]

    word_a_emb = w2v_emb_weight[word_a_index]
    word_b_emb = w2v_emb_weight[word_b_index]
    word_c_emb = w2v_emb_weight[word_c_index]

    analogy_emb = word_a_emb - word_b_emb + word_c_emb
    analogy_top_k = compute_topk_similar(analogy_emb, w2v_emb_weight, k)
    results = [index_to_word[idx] for idx in analogy_top_k]

    return results


# ######################## PART 2: YOUR WORK STARTS HERE ########################


def compute_gender_subspace(
    word_to_embedding: "dict[str, np.array]",
    gender_attribute_words: "list[tuple[str, str]]",
    n_components: int = 1,
) -> np.array:

    gender_attribute_embeddings = []
    for male_word, female_word in gender_attribute_words:

        male_embedding = word_to_embedding[male_word]
        female_embedding = word_to_embedding[female_word]

        mean_embedding = (male_embedding + female_embedding) / 2

        male_embedding = male_embedding - mean_embedding
        female_embedding = female_embedding - mean_embedding

        gender_attribute_embeddings.append(male_embedding)
        gender_attribute_embeddings.append(female_embedding)

    # Run PCA
    pca = PCA(n_components=n_components)
    pca.fit(gender_attribute_embeddings)

    # Return the gender_subspace
    return pca.components_


def project(a: np.array, b: np.array) -> "tuple[float, np.array]":
    scalar = np.dot(a, b) / np.dot(b, b)
    vector_projection = scalar * b
    return scalar, vector_projection


def compute_profession_embeddings(
    word_to_embedding: "dict[str, np.array]", professions: "list[str]"
) -> "dict[str, np.array]":

    profession_embeddings = {}
    for profession in professions:
        embeddings = []
        try:
            embeddings.append(word_to_embedding[profession])
        except KeyError:
            for word in profession.split():
                embeddings.append(word_to_embedding[word])
        profession_embeddings[profession] = np.mean(embeddings, axis=0)

    return profession_embeddings


def compute_extreme_words(
    words: "list[str]",
    word_to_embedding: "dict[str, np.array]",
    gender_subspace: np.array,
    k: int = 10,
    max_: bool = True,
) -> "list[str]":
    gender_subspace = gender_subspace.flatten()
    word_embeddings = compute_profession_embeddings(word_to_embedding, words)
    projection_scalars = {
        word: project(embedding, gender_subspace)[0]
        for word, embedding in word_embeddings.items()
    }
    ordered_words = sorted(
        projection_scalars.items(), key=lambda x: -x[1] if max_ else x[1]
    )
    return [word for word, score in ordered_words[:k]]


def cosine_similarity(a: np.array, b: np.array) -> float:
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    return np.dot(a, b) / (norm_a * norm_b)


def compute_direct_bias(
    words: "list[str]",
    word_to_embedding: "dict[str, np.array]",
    gender_subspace: np.array,
    c: float = 0.25,
):
    gender_subspace = gender_subspace.flatten()
    embeddings = compute_profession_embeddings(word_to_embedding, words)
    similarity_scores = []
    for word, embedding in embeddings.items():
        similarity_scores.append(cosine_similarity(embedding, gender_subspace))
    return np.mean([abs(sim) ** c for sim in similarity_scores])


def weat_association(
    w: str, A: "list[str]", B: "list[str]", word_to_embedding: "dict[str, np.array]"
) -> float:
    w_embedding = word_to_embedding[w]
    A_embeddings = [word_to_embedding[a] for a in A]
    B_embeddings = [word_to_embedding[b] for b in B]

    cos_A_w = [cosine_similarity(w_embedding, a_embed) for a_embed in A_embeddings]
    cos_B_w = [cosine_similarity(w_embedding, b_embed) for b_embed in B_embeddings]

    return np.mean(cos_A_w) - np.mean(cos_B_w)


def weat_differential_association(
    X: "list[str]",
    Y: "list[str]",
    A: "list[str]",
    B: "list[str]",
    word_to_embedding: "dict[str, np.array]",
    weat_association_func: Callable,
) -> float:

    sx_AB = [weat_association(x, A, B, word_to_embedding) for x in X]
    sy_AB = [weat_association(y, A, B, word_to_embedding) for y in Y]

    return np.sum(sx_AB) - np.sum(sy_AB)


def debias_word_embedding(
    word: str, word_to_embedding: "dict[str, np.array]", gender_subspace: np.array
) -> np.array:

    gender_subspace = gender_subspace.flatten()
    word_embed = word_to_embedding[word]
    gender_scalar, gender_vector = project(word_embed, gender_subspace)
    debiased = word_embed - gender_vector
    return debiased


def hard_debias(
    word_to_embedding: "dict[str, np.array]",
    gender_attribute_words: "list[str]",
    n_components: int = 1,
) -> "dict[str, np.array]":

    gender_subspace = compute_gender_subspace(
        word_to_embedding, gender_attribute_words, n_components
    ).flatten()

    return {
        word: debias_word_embedding(word, word_to_embedding, gender_subspace)
        for word, embed in word_to_embedding.items()
    }


if __name__ == "__main__":
    random.seed(2022)
    torch.manual_seed(2022)

    # Parameters (you can change them)
    sample_size = 2500  # Change this if you want to take a subset of data for testing
    batch_size = 64
    n_epochs = 2
    num_words = 50000

    # Load the data
    data_path = "data"  # Use this if running locally

    # If you use GPUs, use the code below:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # ###################### PART 1: TEST CODE ######################
    print("=" * 80)
    print("Running test code for part 1")
    print("-" * 80)

    # Prefilled code showing you how to use the helper functions
    train_raw, valid_raw = load_datasets(data_path)
    if sample_size is not None:
        for key in ["premise", "hypothesis", "label"]:
            train_raw[key] = train_raw[key][:sample_size]
            valid_raw[key] = valid_raw[key][:sample_size]

    full_text = (
        train_raw["premise"]
        + train_raw["hypothesis"]
        + valid_raw["premise"]
        + valid_raw["hypothesis"]
    )

    # Process into indices
    tokens = tokenize_w2v(full_text)

    word_counts = build_word_counts(tokens)
    word_to_index = build_index_map(word_counts, max_words=num_words)
    index_to_word = {v: k for k, v in word_to_index.items()}

    text_indices = tokens_to_ix(tokens, word_to_index)

    # Test build_current_surrounding_pairs
    text = "dogs and cats are playing".split()
    surroundings, currents = build_current_surrounding_pairs(text, window_size=1)
    print(f"text: {text}")
    print(f"surroundings: {surroundings}")
    print(f"currents: {currents}")

    surrounding_expanded, current_expanded = expand_surrounding_words(
        surroundings, currents
    )
    print(f"surrounding_expanded: {surrounding_expanded}")
    print(f"current_expanded: {current_expanded}\n")

    indices = [word_to_index[t] for t in text]
    surroundings, currents = build_current_surrounding_pairs(indices, window_size=1)
    print(f"indices: {indices}")
    print(f"surroundings: {surroundings}")
    print(f"currents: {currents}")

    surrounding_expanded, current_expanded = expand_surrounding_words(
        surroundings, currents
    )
    print(f"surrounding_expanded: {surrounding_expanded}")
    print(f"current_expanded: {current_expanded}")

    # Training CBOW
    print("Training CBOW...")
    sources_cb, targets_cb = cbow_preprocessing(text_indices, window_size=2)

    loader_cb = DataLoader(
        Word2VecDataset(sources_cb, targets_cb),
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate_cbow,
    )

    model_cb = CBOW(num_words=len(word_to_index), embed_dim=200).to(device)
    optimizer = torch.optim.Adam(model_cb.parameters())

    for epoch in range(n_epochs):
        loss = train_w2v(model_cb, optimizer, loader_cb, device=device).item()
        print(f"Loss at epoch #{epoch}: {loss:.4f}")

    # Training Skip-Gram
    print("Training Skip-Gram")
    sources_sg, targets_sg = skipgram_preprocessing(text_indices, window_size=2)

    loader_sg = DataLoader(
        Word2VecDataset(sources_sg, targets_sg),
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate_cbow,
    )

    model_sg = SkipGram(num_words=len(word_to_index), embed_dim=200).to(device)
    optimizer = torch.optim.Adam(model_sg.parameters())

    for epoch in range(n_epochs):
        loss = train_w2v(model_sg, optimizer, loader_sg, device=device).item()
        print(f"Loss at epoch #{epoch}: {loss:.4f}")

    # Test compute_topk_similar
    word_emb = model_sg.emb.weight[0, :]
    w2v_emb_weight = model_sg.emb.weight
    k = 5

    top_k = compute_topk_similar(word_emb, w2v_emb_weight, k)

    # RETRIEVE SIMILAR WORDS
    word = "man"

    similar_words_cb = retrieve_similar_words(
        model=model_cb,
        word=word,
        index_map=word_to_index,
        index_to_word=index_to_word,
        k=5,
    )

    similar_words_sg = retrieve_similar_words(
        model=model_sg,
        word=word,
        index_map=word_to_index,
        index_to_word=index_to_word,
        k=5,
    )

    print(f"(CBOW) Words similar to '{word}' are: {similar_words_cb}")
    print(f"(Skip-gram) Words similar to '{word}' are: {similar_words_sg}")

    # COMPUTE WORDS ANALOGIES
    a = "man"
    b = "woman"
    c = "girl"

    analogies_cb = word_analogy(
        model=model_cb,
        word_a=a,
        word_b=b,
        word_c=c,
        index_map=word_to_index,
        index_to_word=index_to_word,
    )
    analogies_sg = word_analogy(
        model=model_sg,
        word_a=a,
        word_b=b,
        word_c=c,
        index_map=word_to_index,
        index_to_word=index_to_word,
    )

    print(f"CBOW's analogies for {a} - {b} + {c} are: {analogies_cb}")
    print(f"Skip-gram's analogies for {a} - {b} + {c} are: {analogies_sg}")

    ###################### PART 1: TEST CODE ######################

    # Prefilled code showing you how to use the helper functions
    print("Loading glove embeddings...")
    word_to_embedding = load_glove_embeddings("data/glove/glove.6B.300d.txt")

    print("Loading professions...")
    professions = load_professions("data/professions.tsv")

    print("Loading gender attribute_words...")
    gender_attribute_words = load_gender_attribute_words(
        "data/gender_attribute_words.json"
    )

    # === Section 2.1 ===
    gender_subspace = compute_gender_subspace(
        word_to_embedding, gender_attribute_words=[["man", "woman"], ["boy", "girl"]]
    ).flatten()

    # === Section 2.2 ===
    a = word_to_embedding["doctor"]
    b = word_to_embedding["nurse"]
    scalar_projection, vector_projection = project(a, gender_subspace)

    # === Section 2.3 ===
    profession_to_embedding = compute_profession_embeddings(
        word_to_embedding, professions
    )

    # === Section 2.4 ===
    positive_profession_words = compute_extreme_words(
        professions, word_to_embedding, gender_subspace, k=10, max_=True
    )
    negative_profession_words = compute_extreme_words(
        professions, word_to_embedding, gender_subspace, k=10, max_=False
    )

    print(f"Max profession words: {positive_profession_words}")
    print(f"Min profession words: {negative_profession_words}")

    # # === Section 2.5 ===
    direct_bias_professions = compute_direct_bias(
        professions, word_to_embedding, gender_subspace, c=0.25
    )

    # # === Section 2.6 ===

    # Prepare attribute word sets for testing
    A = ["male", "man", "boy", "brother", "he", "him", "his", "son"]
    B = ["female", "woman", "girl", "sister", "she", "her", "hers", "daughter"]

    # Prepare target word sets for testing
    X = ["doctor", "mechanic", "engineer"]
    Y = ["nurse", "artist", "teacher"]

    word = "doctor"
    weat_association_ex = weat_association("cowboy", A, B, word_to_embedding)
    weat_differential_association_ex = weat_differential_association(
        X, Y, A, B, word_to_embedding, weat_association
    )

    # === Section 3.1 ===
    debiased_word_to_embedding_ex = debias_word_embedding(
        word, word_to_embedding, gender_subspace
    )

    debiased_word_to_embedding = hard_debias(
        word_to_embedding, gender_attribute_words, n_components=1
    )

    # === Section 3.2 ===
    direct_bias_professions = compute_direct_bias(
        professions, profession_to_embedding, gender_subspace, c=0.25
    )
    print(f"DirectBias Professions: {direct_bias_professions:.2f}")

    direct_bias_professions_debiased = compute_direct_bias(
        professions, debiased_word_to_embedding, gender_subspace, c=0.25
    )
    print(f"DirectBias Professions (debiased): {direct_bias_professions_debiased:.2f}")

    X = [
        "math",
        "algebra",
        "geometry",
        "calculus",
        "equations",
        "computation",
        "numbers",
        "addition",
    ]

    Y = [
        "poetry",
        "art",
        "dance",
        "literature",
        "novel",
        "symphony",
        "drama",
        "sculpture",
    ]

    # Also run this test for debiased profession representations.
    p_value = p_value_permutation_test(X, Y, A, B, word_to_embedding)
    print(f"p-value: {p_value:.4f}")

    p_value_debiased = p_value_permutation_test(X, Y, A, B, debiased_word_to_embedding)
    print(f"p-value debiased: {p_value:.4f}")

    print("Done!")
