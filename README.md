# Movie Recommendation App — Assignment Part 2

## Live Demo (Internet URL)
You can test the application here:  
https://movie-frontend-714848336619.europe-west6.run.app/

## Similarity Computation Method (Cold-Start “Similar Users”)
Because the web app user is a cold-start user (no existing `userId` in the dataset), we identify similar users directly from the historical ratings table using an overlap-based approach:

1. The user likes/selects a list of movies (MovieLens `movieId`s).
2. We find candidate users who rated any of these liked movies highly (rating ≥ 4.0).
3. For each candidate user, we compute a similarity score called **overlap** = the number of liked movies that user also rated ≥ 4.0.
4. We select the **top-k** most similar users (top 20 by overlap).
5. We recommend movies that these similar users rated highly (rating ≥ 4.0), rank candidates by an aggregate score (average rating among similar users), and return the top results.
6. Finally, we remove any movies already liked by the current user to avoid duplicates.

This method is interpretable: a dataset user is “similar” if they highly-rated many of the same movies as the current user, and recommendations come from what those similar users also liked.
