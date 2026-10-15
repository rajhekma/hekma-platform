package com.hekma.identity.repository;

import com.hekma.identity.domain.Authority;
import com.hekma.identity.domain.UserAuthorityEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.UUID;

@Repository
public interface UserAuthorityRepository extends JpaRepository<UserAuthorityEntity, UUID> {

    List<UserAuthorityEntity> findByUser_Id(UUID userId);

    @Query("SELECT ua.authority FROM UserAuthorityEntity ua WHERE ua.user.id = :userId")
    List<Authority> findAuthoritiesByUserId(@Param("userId") UUID userId);
}
